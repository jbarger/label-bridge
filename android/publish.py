"""Publish Label Bridge to Google Play from the command line.

Uses the Google Play Developer API with a service account. One-time setup is
described in docs/play-store.md ("Publishing from the command line").

    python android/publish.py status
    python android/publish.py upload [--track alpha] [--build] [--rollout]
    python android/publish.py listing [--images]
    python android/publish.py testers --group testers@googlegroups.com
    python android/publish.py promote --from alpha --to production [--rollout]

Every command works on one "edit" (Play's transaction). Nothing changes on Play
until the edit is committed, and --dry-run validates without committing.

Releases are created as drafts unless --rollout is given. While the app has
never been published, Play only accepts drafts, so send the first release for
review from Play Console.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PACKAGE = "com.labelbridge.app"
ANDROID = Path(__file__).resolve().parent
REPO = ANDROID.parent
PLAY_DIR = ANDROID / "play"
AAB = ANDROID / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"
DEFAULT_KEY = Path(os.environ.get("APPDATA", str(Path.home()))) / "Label Bridge Dev" / "play-service-account.json"

# Play track names: "alpha" is the default closed-testing track, "beta" is open testing.
TRACKS = ("internal", "alpha", "beta", "production")

# listing image type -> file(s) in the repo
IMAGES = {
    "icon": [REPO / "docs" / "store" / "icon-512.png"],
    "featureGraphic": [REPO / "docs" / "store" / "feature-graphic.png"],
    "phoneScreenshots": sorted((PLAY_DIR / "screenshots" / "phone").glob("*.png")),
}


def service(key_path: Path):
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("Missing libraries. Run: pip install -r android/requirements-publish.txt")
    if not key_path.exists():
        sys.exit(f"Service account key not found: {key_path}\n"
                 "Set LABELBRIDGE_PLAY_KEY or pass --key. See docs/play-store.md.")
    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=["https://www.googleapis.com/auth/androidpublisher"])
    return build("androidpublisher", "v3", credentials=creds, cache_discovery=False)


class Edit:
    """Context manager around a Play edit: commits on success, deletes on error or dry run."""

    def __init__(self, api, dry_run: bool):
        self.api, self.dry_run = api, dry_run
        self.edits = api.edits()

    def __enter__(self):
        self.id = self.edits.insert(packageName=PACKAGE, body={}).execute()["id"]
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None and not self.dry_run:
            self.edits.commit(packageName=PACKAGE, editId=self.id).execute()
            print("Committed to Google Play.")
        else:
            self.edits.delete(packageName=PACKAGE, editId=self.id).execute()
            if exc_type is None:
                print("Dry run: validated, nothing changed on Google Play.")
        return False

    def call(self, resource: str, method: str, **kw):
        return getattr(getattr(self.edits, resource)(), method)(packageName=PACKAGE, editId=self.id, **kw).execute()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def release_notes() -> list[dict]:
    notes = []
    for f in sorted((PLAY_DIR / "release_notes").glob("*.txt")):
        text = read(f)
        if len(text) > 500:
            sys.exit(f"{f.name}: release notes are {len(text)} characters; Play allows 500.")
        notes.append({"language": f.stem, "text": text})
    return notes


def version_name() -> str:
    m = re.search(r"versionName\s+['\"]([^'\"]+)", (ANDROID / "app" / "build.gradle").read_text())
    return m.group(1) if m else "?"


def build_bundle() -> None:
    if not os.environ.get("JAVA_HOME"):
        sys.exit("Set JAVA_HOME to a JDK 17+ before using --build.")
    gradlew = ANDROID / ("gradlew.bat" if os.name == "nt" else "gradlew")
    subprocess.run([str(gradlew), "bundleRelease"], cwd=ANDROID, check=True)


# ---- commands ---------------------------------------------------------------

def cmd_status(api, args) -> None:
    with Edit(api, dry_run=True) as e:
        details = e.call("details", "get")
        print(f"{PACKAGE}  default language: {details.get('defaultLanguage')}  contact: {details.get('contactEmail') or '-'}")
        for t in e.call("tracks", "list").get("tracks", []):
            releases = t.get("releases") or []
            if not releases:
                print(f"  {t['track']:<11} (empty)")
            for r in releases:
                frac = f" {r['userFraction']:.0%}" if "userFraction" in r else ""
                print(f"  {t['track']:<11} {r.get('name', '')!s:<14} codes={r.get('versionCodes', [])} {r['status']}{frac}")
        for lst in e.call("listings", "list").get("listings", []):
            print(f"  listing {lst['language']}: {lst.get('title')!r}")
        shots = e.call("images", "list", language="en-US", imageType="phoneScreenshots").get("images", [])
        print(f"  phone screenshots on Play: {len(shots)}")


def cmd_upload(api, args) -> None:
    if args.build:
        build_bundle()
    if not AAB.exists():
        sys.exit(f"No bundle at {AAB}. Build it first (or pass --build).")
    from googleapiclient.http import MediaFileUpload
    with Edit(api, args.dry_run) as e:
        media = MediaFileUpload(str(AAB), mimetype="application/octet-stream", resumable=True)
        bundle = e.edits.bundles().upload(packageName=PACKAGE, editId=e.id, media_body=media).execute()
        code = bundle["versionCode"]
        print(f"Uploaded bundle: versionCode {code}")
        release = {"name": f"{code} ({version_name()})", "versionCodes": [str(code)],
                   "releaseNotes": release_notes(), "status": "completed" if args.rollout else "draft"}
        if args.rollout and args.fraction:
            release.update(status="inProgress", userFraction=args.fraction)
        e.call("tracks", "update", track=args.track, body={"track": args.track, "releases": [release]})
        print(f"Track {args.track}: release {release['name']} as {release['status']}")


def cmd_promote(api, args) -> None:
    with Edit(api, args.dry_run) as e:
        src = e.call("tracks", "get", track=args.source)
        releases = [r for r in src.get("releases", []) if r.get("versionCodes")]
        if not releases:
            sys.exit(f"Nothing on {args.source} to promote.")
        r = releases[0]
        new = {"name": r.get("name"), "versionCodes": r["versionCodes"], "releaseNotes": r.get("releaseNotes", []),
               "status": "completed" if args.rollout else "draft"}
        if args.rollout and args.fraction:
            new.update(status="inProgress", userFraction=args.fraction)
        e.call("tracks", "update", track=args.dest, body={"track": args.dest, "releases": [new]})
        print(f"{args.source} -> {args.dest}: {new['name']} as {new['status']}")


def cmd_listing(api, args) -> None:
    from googleapiclient.http import MediaFileUpload
    with Edit(api, args.dry_run) as e:
        for lang_dir in sorted((PLAY_DIR / "listing").iterdir()):
            body = {"language": lang_dir.name,
                    "title": read(lang_dir / "title.txt"),
                    "shortDescription": read(lang_dir / "short_description.txt"),
                    "fullDescription": read(lang_dir / "full_description.txt")}
            limits = {"title": 30, "shortDescription": 80, "fullDescription": 4000}
            for k, n in limits.items():
                if len(body[k]) > n:
                    sys.exit(f"{lang_dir.name} {k} is {len(body[k])} characters; Play allows {n}.")
            e.call("listings", "update", language=lang_dir.name, body=body)
            print(f"Listing {lang_dir.name}: text updated")
        if args.images:
            for kind, files in IMAGES.items():
                files = [f for f in files if f.exists()]
                if not files:
                    print(f"  {kind}: no files, left as is")
                    continue
                e.call("images", "deleteall", language="en-US", imageType=kind)
                for f in files:
                    e.edits.images().upload(packageName=PACKAGE, editId=e.id, language="en-US", imageType=kind,
                                            media_body=MediaFileUpload(str(f), mimetype="image/png")).execute()
                print(f"  {kind}: uploaded {len(files)} file(s)")


def cmd_testers(api, args) -> None:
    with Edit(api, args.dry_run) as e:
        e.call("testers", "update", track=args.track, body={"googleGroups": args.group})
        print(f"Track {args.track} testers: {', '.join(args.group)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--key", type=Path, default=Path(os.environ.get("LABELBRIDGE_PLAY_KEY", DEFAULT_KEY)),
                   help="service account JSON key (default: %(default)s)")
    p.add_argument("--dry-run", action="store_true", help="validate everything but don't commit")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show tracks, releases and listing")

    u = sub.add_parser("upload", help="upload the release bundle to a track")
    u.add_argument("--track", choices=TRACKS, default="alpha", help="default: alpha (closed testing)")
    u.add_argument("--build", action="store_true", help="run gradlew bundleRelease first")
    u.add_argument("--rollout", action="store_true", help="roll out instead of saving as a draft")
    u.add_argument("--fraction", type=float, help="staged rollout fraction, e.g. 0.2 (with --rollout)")

    pr = sub.add_parser("promote", help="copy the release on one track to another")
    pr.add_argument("--from", dest="source", choices=TRACKS, required=True)
    pr.add_argument("--to", dest="dest", choices=TRACKS, required=True)
    pr.add_argument("--rollout", action="store_true")
    pr.add_argument("--fraction", type=float)

    li = sub.add_parser("listing", help="push store listing text from android/play/listing")
    li.add_argument("--images", action="store_true", help="also replace icon, feature graphic and screenshots")

    te = sub.add_parser("testers", help="set the Google Groups allowed on a testing track")
    te.add_argument("--track", choices=TRACKS[:3], default="alpha")
    te.add_argument("--group", action="append", required=True, help="Google Group email (repeatable)")

    args = p.parse_args()
    api = service(args.key)
    {"status": cmd_status, "upload": cmd_upload, "promote": cmd_promote,
     "listing": cmd_listing, "testers": cmd_testers}[args.cmd](api, args)


if __name__ == "__main__":
    main()
