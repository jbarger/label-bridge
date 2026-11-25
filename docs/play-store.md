# Google Play release checklist

Everything here is for the Play Console. It is not shown in the app.

## Files
- **App bundle to upload:** `android/app/build/outputs/bundle/release/app-release.aab`
  (build it with `android\gradlew.bat bundleRelease`)
- **App icon (512×512):** `docs/store/icon-512.png`
- **Feature graphic (1024×500):** `docs/store/feature-graphic.png`
- **Phone screenshots:** take 2–4 on the phone (setup screen, Share sheet with
  Label Bridge, the "✓ printed" popup, the Print dialog).

## Signing
- Use **Play App Signing** (the default). `android/labelbridge-upload.jks` is the
  *upload* key, and its password is in `android/keystore.properties`. Neither is in git.
  **Back up both files** somewhere safe, such as a password manager. If you lose
  them, Play support can reset the upload key, but that takes a few days.

## Store listing
The listing text lives in `android/play/listing/en-US/` (`title.txt`,
`short_description.txt`, `full_description.txt`) and release notes in
`android/play/release_notes/en-US.txt`. Edit those files and push them with
`publish.py listing` (see below) rather than editing in Play Console.

**Category:** Business
**Contact email:** use a contact address you're happy to make public
**Website:** https://github.com/jbarger/label-bridge
**Privacy policy URL:** https://jbarger.github.io/label-bridge/privacy

## App content answers
- **Ads:** Yes, the app contains ads.
- **Target audience:** 18 and over (not designed for children).
- **Data safety:**
  - Data collected: *Device or other IDs* (advertising ID), *App interactions*,
    *Diagnostics*, and *Approximate location*. All of this comes from the Google
    Mobile Ads SDK and is used for advertising and analytics.
  - Data shared: the same items, shared with Google for advertising.
  - Encrypted in transit: Yes. AdMob traffic is HTTPS. The label PDFs go only to
    your own PC on your LAN and are not "collected" under Play's definition.
  - Users can request deletion: not applicable, because no account is created
    and no data is stored by the developer.
- **Advertising ID declaration:** Yes, it is used for advertising.
- **Government / financial / health features:** None.

## AdMob
1. Create an AdMob account at admob.google.com. Add the app as an Android app
   (you can link it to the Play listing once it is published) and create one
   **Banner** ad unit.
2. Create `android/admob.properties` (it isn't committed to git):
   ```
   admobAppId=ca-app-pub-XXXXXXXXXXXXXXXX~YYYYYYYYYY
   bannerId=ca-app-pub-XXXXXXXXXXXXXXXX/ZZZZZZZZZZ
   ```
   Without this file the build uses Google's public **test** ads, which earn nothing.
3. In AdMob, open **Privacy & messaging** and publish a **GDPR** message (and a
   US-states message). The app already shows it through the User Messaging Platform.
4. **app-ads.txt:** AdMob checks `https://<your website's domain>/app-ads.txt`.
   For a github.io site this must be at the domain root, so create a repo named
   `jbarger.github.io` that contains `app-ads.txt` with the line AdMob gives you:
   `google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0`.
   Then set the Play listing's website to `https://jbarger.github.io`.

## Publishing from the command line
`android/publish.py` talks to the Google Play Developer API, so a new release
doesn't need Play Console:

```powershell
pip install -r android\requirements-publish.txt
python android\publish.py status                      # tracks, releases, listing
python android\publish.py upload --build               # build + upload to closed testing as a draft
python android\publish.py upload --track alpha --rollout   # ...or roll it out to testers
python android\publish.py promote --from alpha --to production --rollout --fraction 0.2
python android\publish.py listing --images             # push listing text, icon, graphic, screenshots
python android\publish.py testers --group label-bridge-testers@googlegroups.com
```

Add `--dry-run` before the command to validate without changing anything.
Phone screenshots go in `android/play/screenshots/phone/*.png`.

**One-time setup (already done for this app):**
1. Google Cloud project `label-bridge-publishing` with the *Google Play Android
   Developer API* enabled.
2. Service account `play-publisher@label-bridge-publishing.iam.gserviceaccount.com`
   with a JSON key, stored at `%APPDATA%\Label Bridge Dev\play-service-account.json`
   (or point `LABELBRIDGE_PLAY_KEY` at it). **Never commit this file.** It can
   publish the app. If it leaks, delete the key in Cloud Console → IAM → Service
   accounts → Keys and create a new one.
3. In Play Console → Users and permissions, that service account has access to
   Label Bridge only: drafts, testing and production releases, tester lists and
   store presence.

The API can't do these, so they stay in Play Console: the content rating
questionnaire and other App content forms, the first release of a brand-new app
("Send for review"), and adding testers by individual email address (the API
only takes Google Groups).

## Personal developer accounts: testing rule
New personal accounts must run a **closed test with at least 12 testers for 14
days in a row** before they can apply for production access. Upload the AAB to
a closed-testing track, add 12+ Gmail addresses (friends or family who opt in
through the link), keep them opted in for 14 days, then apply for production.
