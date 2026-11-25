# Label Bridge

Print shipping labels on a 4x6 thermal label printer **without ever opening a print
dialog**. That works from your PC's folders and from your Android phone.

- **Windows:** drop a label PDF into the *Labels to Print* folder and it prints.
- **Android:** tap **Share → Label Bridge** on any label PDF, or use the normal
  **⋮ → Print** menu, and it prints on the label printer at your PC.

Carrier PDFs are usually a full letter page with the label in one corner plus
instructions. Label Bridge finds the label on the page, crops to it, rotates it to
portrait, and scales it to fill the 4x6 label. It renders in pure black and white
at the printer's own resolution, so barcodes stay sharp.

Works with any 4x6 printer that has a Windows driver, for example Rollo, Zebra,
MUNBYN, iDPRT, Polono, Phomemo, Jadens, Arkscan and D450.

## Install

### Windows (required)
1. Download **LabelBridge-Setup.exe** from the
   [latest release](https://github.com/jbarger/label-bridge/releases/latest) and run it.
2. Leave the three options ticked: start with Windows, allow phones on home Wi-Fi,
   and a desktop shortcut.
3. The settings window opens. Pick your printer (it usually picks itself), then
   click **Save and print a test label**.

Label Bridge then runs in the notification area (the orange label icon). Right-click
the icon for the labels folder, Settings, a test print, the log, or Quit.

Windows SmartScreen may warn that the installer is unrecognised, because it isn't
code-signed. Click **More info → Run anyway**.

### Android (optional)
1. Install **Label Bridge** from Google Play.
2. Open it, type the **pairing code** shown in the PC's Label Bridge settings,
   and tap **Find my PC on this Wi-Fi**.
3. To use the ⋮ → Print menu as well, tap **Turn on in the Print menu…** once.

The phone and PC must be on the same Wi-Fi, and Windows must treat that network as
**Private**. The settings window warns you if it is set to Public.

## Everyday use

| From | How |
|---|---|
| PC | Save or drag a PDF into **Documents\Label Bridge\Inbox** (desktop shortcut: *Labels to Print*) |
| Phone, Share | On a label PDF in Gmail, Drive, Files or Chrome, tap **Share → Label Bridge**. You can select several. |
| Phone, Print menu | In any app, tap **⋮ → Print**, choose the printer ending in **(Label Bridge)**, and print. Leave the paper size on Letter. |
| Anywhere | In settings, add a synced **Google Drive / OneDrive** folder under *Also watch*. Any PDF saved into it from anywhere prints. |

After printing, the PDF moves to `Printed\`. If something goes wrong it moves to
`Failed\`, with a `.error.txt` explaining why, and the tray icon pops up a
notification. `Previews\` keeps a PNG of exactly what was sent to the printer.

## Settings

The settings window covers the printer, label size, phone pairing, watched folders
and preview-only mode. **More settings…** opens `config.json`
(`%LOCALAPPDATA%\Label Bridge\config.json`) for the fine-tuning keys below.
Changes take effect within a couple of seconds.

| key | what it does |
|---|---|
| `margin_in` | white border around the label. Raise it if the edges get clipped |
| `min_gap_in` | how big a blank gap must be to separate the label from other page content. Lower it if instruction text is being included; raise it if part of the label is cut off |
| `rotate_landscape` | `"clockwise"` or `"counterclockwise"` for landscape labels |
| `bw_threshold` | 0–255; raise it to print light-grey text darker |
| `label_width_in` / `label_height_in` | label size (default 4 × 6) |
| `server_port` | port the phone app connects to (default 8765; restart after changing) |

## How it works

```
Phone app ──HTTP (LAN, pairing code)──▶ phone_server.py ─┐
Drive/OneDrive folder ─────────────────────────────────┼─▶ Inbox ─▶ crop ▶ rotate ▶ scale ▶ print (GDI)
Labels to Print folder ────────────────────────────────┘
```

- `windows/labelprinter.py` is the hot folder, the cropping (XY-cut on blank gaps,
  largest block wins) and the printing. It picks the driver's 4x6 / 100x150 mm
  paper size automatically.
- `windows/phone_server.py` is a small HTTP endpoint on port 8765, advertised over
  mDNS as `_labelprinter._tcp`. Requests without the pairing code are refused.
- `android/` is the Android app: share target, `PrintService` and a setup screen.
  It has one banner ad (AdMob) on the setup screen and on the print popup.

Nothing leaves your network except the phone app's ad requests. See the
[privacy policy](docs/privacy.md).

## Building from source

**Windows installer.** Needs Python 3.10+ and Inno Setup 6
(`winget install JRSoftware.InnoSetup`):
```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build.ps1   # -> dist\LabelBridge-Setup-<version>.exe
```
To run from source instead: `pip install -r windows\requirements.txt`, then
`python windows\labelprinter.py watch`. Other commands: `settings`, `test`,
`printers`, `preview FILE.pdf`, `print FILE.pdf`.

**Android.** Needs JDK 17+ and the Android SDK (set `ANDROID_HOME`, or put
`sdk.dir=...` in `android/local.properties`):
```powershell
cd android
python make_icon.py
.\gradlew.bat assembleDebug      # or bundleRelease for Play
```
Release signing reads `android/keystore.properties`, and real ad IDs come from
`android/admob.properties`. Neither file is committed, and without them the build uses
Google's test ads. See [docs/play-store.md](docs/play-store.md) for the Play
release checklist.

## License

MIT
