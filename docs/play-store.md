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
**App name:** Label Bridge

**Short description (80 max):**
Print 4x6 shipping labels from your phone on the label printer at your PC.

**Full description:**
Label Bridge sends shipping-label PDFs from your phone to the 4x6 thermal label
printer plugged into your Windows PC. It works with Rollo, Zebra, MUNBYN, iDPRT, Polono,
D450 and other 4x6 printers. Labels print full-size and sharp.

• Share any label PDF from Gmail, Drive, Files, eBay, Etsy, Pirate Ship or a
  carrier site, and choose Label Bridge.
• Or use the regular ⋮ → Print menu in any app and pick your label printer.
• Select several PDFs at once to print a whole batch.
• Full-page carrier PDFs (USPS, UPS, FedEx and others) are cropped to just the label automatically,
  rotated if needed, and scaled to fill the 4x6 label.

Requires the free Label Bridge program for Windows, available from
github.com/jbarger/label-bridge. The phone and PC must be on the same Wi-Fi.
Your labels go straight from your phone to your PC and never pass through
any server.

**Category:** Business (or Productivity)
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

## Personal developer accounts: testing rule
New personal accounts must run a **closed test with at least 12 testers for 14
days in a row** before they can apply for production access. Upload the AAB to
a closed-testing track, add 12+ Gmail addresses (friends or family who opt in
through the link), keep them opted in for 14 days, then apply for production.
