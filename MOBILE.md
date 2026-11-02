# Ship teachertranslate as a mobile app

This repo is mobile-ready. Your app is a standard web app (Vite + React)
with a backend you own, wrapped into a real iOS/Android app with
[Capacitor](https://capacitorjs.com) 8. The native projects (`ios/`,
`android/`) are generated on demand — never committed — by
`mobile/setup.mjs`, which applies everything they need every time: your
store identity, the version, the sign-in return channel, the App Store
hygiene, the app icon from your live site, and your app's own native
settings from `mobile/native.json` (below — the one place to put them).

## Path A: your EscapeBase44 success page (no Mac needed)

The "Ship to the App Store" card runs the **Mobile release** workflow of
this repo on GitHub's machines and shows you every step as it happens.

- **iPhone** — paste your App Store Connect API key once (the card says
  where to get it) and click. The workflow first asks Apple whether the key
  works, whether your app's record exists in App Store Connect and which
  version to build, turns on for your app every capability its settings
  need, then builds on a cloud Mac and uploads to TestFlight. Anything that
  stops it is explained on the card in plain words, with the one thing to do
  next.
- **Android** — one click. The first click creates your Google Play upload
  key (kept as this repo's secrets); every build produces a signed Play
  bundle (`.aab`, what the Play Console takes) and a signed `.apk` that
  installs on any Android phone (and over the one before it), published as
  this repo's **Mobile builds** release, with download buttons on the card.
- **Google Play, automatically** — once your app exists in Play Console (the
  first bundle is uploaded by hand there; Google's rule), every Android
  build also lands in your Internal testing track, through the service
  account you give the card for in-app purchases (give it "Release apps to
  testing tracks" in Play Console → Users and permissions).
- **Push notifications** — the card takes your Apple push key and your
  Firebase key; sending is `SendPushNotification` from your backend
  functions, as on Base44 (see below).
- **Sign in with Apple** — built into the iPhone app with nothing to set
  up (App Store review requires it next to Google or Microsoft sign-in).

Builds run on your own GitHub account's minutes once the repo is yours (a
cloud Mac counts ten to one; an iPhone build is ~12 minutes of it), which
is why the card asks you to transfer the repo before the first iPhone build.

## Path B: your own machine

```
npm run mobile:setup     # installs Capacitor, creates ios/ + android/, applies everything
npm run mobile:ios       # the same for iPhone, then opens Xcode (Mac only)
npm run mobile:android   # the same for Android, then opens Android Studio
```

From Xcode: Product → Archive → Distribute App. From Android Studio:
Build → Generate Signed App Bundle. The same setup script the workflow runs
prepares the projects, so what you open is what the cloud builds. Run one of
these again after changing `mobile/native.json` or adding a plugin.

## Native features: `mobile/native.json`

Your app's pages already use the phone's location, camera, microphone,
downloads, share and print inside the app (below). Anything more — tracking
location in the background, health data, NFC, Face ID, a native barcode
scanner — is a Capacitor **plugin** plus a few **native settings** (a reason
shown to the person, a background mode, an entitlement, an Android
permission). The native projects are generated
fresh on every build, so those settings live in one file of your own,
`mobile/native.json`, which every build applies. Never edit `ios/` or
`android/` to add a setting: they are not kept.

1. **Add the plugin to the app**: `npm install <plugin>`, a version made
   for Capacitor 8. For the iPhone it must come as a Swift package (it has a
   `Package.swift` asking for Capacitor 8): the build stops and names a
   plugin made for an older Capacitor, and warns about one with no Swift
   package (it is left out of the iPhone app). A plugin that needs a newer
   Android or iOS than Capacitor's own raises the app's lowest supported
   version by itself (the health plugin: Android 8).
2. **Put its settings in `mobile/native.json`** (create the file):

```json
{
  "orientation": "default",
  "splash": { "backgroundColor": "#ff8a34", "image": "assets/splash-logo.png" },
  "statusBar": { "style": "light", "hidden": false },
  "links": true,
  "ios": {
    "infoPlist": { "NSFaceIDUsageDescription": "Sign in faster with Face ID." },
    "entitlements": { }
  },
  "android": {
    "permissions": ["USE_BIOMETRIC"],
    "manifest": { "root": [], "application": [], "activity": [] }
  },
  "capacitor": { }
}
```

   Every key is optional; the names are Expo's (app.json) where the two meet.
   - `orientation` — `default` (the phone turns the app), `portrait` or `landscape`.
   - `splash` — the splash screen: its colour (`backgroundColor`, and
     `darkBackgroundColor` if dark mode should differ) and the logo on it
     (`image`: a PNG in the repo, or `false` for the colour alone; the app
     icon by default). On Android 12 and later the logo shows inside a circle.
   - `statusBar` — `style`: `light` (white text, for a dark app), `dark` or
     `auto`; `hidden: true` hides it (the page still keeps clear of the
     camera notch; Android's own launch splash still shows it for a moment).
   - `links` — `true`: a link to your app's address (and to any custom
     domain you attach) opens the installed app at that page, on iPhone and
     Android; your backend serves the two files the phones check. Build
     again after attaching a new domain.
   - `ios.infoPlist` — keys for the app's Info.plist. Yours replace the
     kit's: write the reasons the phone shows the person (`NS…UsageDescription`)
     in your app's own words — Apple rejects vague ones.
   - `ios.entitlements` — entitlements the app is signed with. The build
     turns on for your app each capability they need (HealthKit, NFC,
     Associated Domains…) and checks Apple kept every one in the signed app.
   - `android.permissions` — permission names (`CAMERA`, `USE_BIOMETRIC`,
     `ACCESS_BACKGROUND_LOCATION`; a full name like
     `android.permission.health.READ_STEPS` works too).
   - `android.blockedPermissions` — permissions taken out of the app, whoever
     declares them (a plugin declares everything it might need): names, or a
     family like `android.permission.health.*` — every one of it but those
     you list in `android.permissions`.
   - `android.manifest` — raw XML, as strings, for the manifest's root, its
     `<application>` and the main `<activity>`.
   - `capacitor` — merged into the Capacitor config the app is built with (a
     plugin's own settings, `android.useLegacyBridge` …).
3. **Call the plugin from your code** only inside the app:
   `if (window.eb44?.isMobileApp()) { … }`. A new plugin or setting reaches
   phones with the next store build.

What each feature needs (Capacitor 8 plugins with a Swift package, checked
2026-10-21):

- **Location in the background** — `@capgo/background-geolocation`.
  `ios.infoPlist`: `"UIBackgroundModes": ["location"]`,
  `"NSLocationWhenInUseUsageDescription": "<why>"` and
  `"NSLocationAlwaysAndWhenInUseUsageDescription": "<why>"`;
  `capacitor`: `{ "android": { "useLegacyBridge": true } }` (or Android stops
  the updates after five minutes in the background). The plugin declares its
  Android permissions and service itself; Android shows a notification while
  it tracks.
- **Health data** (Apple Health, Health Connect) — `@capgo/capacitor-health`.
  `ios.entitlements`: `{ "com.apple.developer.healthkit": true,
  "com.apple.developer.healthkit.access": [] }`; `ios.infoPlist`:
  `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription`. On
  Android the plugin declares reading and writing every kind of health data,
  and Google Play refuses an app that declares health data it does not use:
  list the ones your app reads and writes in `android.permissions`
  (`android.permission.health.READ_STEPS`, …) and block the rest with
  `"blockedPermissions": ["android.permission.health.*"]`.
  Health Connect shows your privacy policy from `public/privacypolicy.html`
  of this app; it must be the one your Play listing links to.
- **Barcode and QR scanning** — `@capacitor/barcode-scanner`.
  `android.permissions`: `["CAMERA"]`; `ios.infoPlist`:
  `NSCameraUsageDescription` in your words.
- **NFC** — `@capgo/capacitor-nfc`. `ios.infoPlist`:
  `NFCReaderUsageDescription`; `ios.entitlements`:
  `{ "com.apple.developer.nfc.readersession.formats": ["TAG"] }` (it reads
  NDEF tags too; App Store Connect refuses an upload that lists `NDEF`). The
  plugin declares Android's NFC permission. iPhones read NFC; the iPhone
  Simulator does not.
- **Face ID / fingerprint** — `@capgo/capacitor-native-biometric`.
  `ios.infoPlist`: `NSFaceIDUsageDescription`; `android.permissions`:
  `["USE_BIOMETRIC"]`.
- **Keep the screen on** — `@capacitor-community/keep-awake`; no settings.
- **Links that open the app** — `"links": true`; nothing to install.

## Store accounts and costs (paid to Apple/Google, not to anyone else)

- Apple App Store: **$99/year** ([enroll](https://developer.apple.com/programs/enroll/)).
  Individuals must be 18+; companies need a D-U-N-S number. The card needs
  an App Store Connect API **Team key with Admin access** (Apple gates
  cloud signing behind it) and your app's record in App Store Connect —
  the card tells you exactly when to create it and with which bundle id.
- Google Play: **$25 one-time** ([console](https://play.google.com/console/signup)).
  Personal accounts created after Nov 2023 must run a **closed test with
  12 testers for 14 days** before going live. Organization accounts skip
  this — worth it if you have a registered business.

## Identity and versions — where each fact lives

Non-secret facts live in `.escapebase44/config.json` (`env`), the same
file the rest of the app's configuration lives in; the card writes them
and every build reads them.

- **iPhone bundle id** — `MOBILE_IOS_BUNDLE_ID`, default `com.eb44.app69fc81cf4f6a0ae5ab617e2b`.
  Permanent once your App Store record exists. **Already in the App Store
  through Base44?** Base44 published under its own id, `com.base<your Base44
  app id>.app`; the card detects that listing and offers to keep it — your
  ratings, reviews and installs stay, and the build lands as an update.
  Choose before the first build.
- **Android package name** — `MOBILE_ANDROID_PACKAGE`, default
  `com.eb44.app69fc81cf4f6a0ae5ab617e2b`. Permanent once your Play listing exists. **Already on
  Google Play?** Keep the package name you published under (Base44's is
  `com.base<your Base44 app id>.app`; the card offers it), and either upload
  the keystore you signed with or — when Base44 signed your uploads — ask
  Google to accept this repo's upload key instead: Google's own steps are its
  help page "Use Play App Signing"
  (https://support.google.com/googleplay/android-developer/answer/9842756),
  section "Request an upload key reset", with the `upload_certificate.pem`
  the card gives you as the certificate. Once Google accepts it,
  every build here is an update of your listing.
  `MOBILE_ANDROID_VERSION_CODE_BASE` is the highest version code you ever
  uploaded there; each build's code is that plus the run number.
- **The name under the icon** — `appName` in `capacitor.config.json`,
  your app's name. Change it there; the next build carries it.
- **Apple team id** — `APPLE_TEAM_ID` (Membership details on
  developer.apple.com), written by the card with your key.
- **Versions** — computed per build, never typed: for iPhone the workflow
  reads App Store Connect and uses the highest version you have (bumped if
  that one already shipped) and a build number above everything uploaded
  before; for Android `1.0` unless you pass one. The workflow's `version`
  input overrides both.
- **Sign-in return scheme** — `eb44-69fc81cf4f6a0ae5ab617e2b` (used by https://teachertranslate.eb44.app/login inside
  the app). Derived from your app id; nothing to change.

Secrets (the Apple key, the Play keystore, the push keys) live where every
secret of this app lives: the repo's GitHub Actions secrets. The card
writes them; `npm run dev` ejects them to your machine when you need them.

## Sign in with Apple

Built into the iPhone app, because Apple's review asks for it beside any
social login (guideline 4.8). It exists there and nowhere else: not on the
web, not in the Android app.

- The login page shows "Sign in with Apple" inside the iPhone app whenever
  Google or Microsoft sign-in is on for the app. The app asks Apple
  directly; the backend verifies Apple's identity token against Apple's
  published keys, for this app's bundle id, with a one-time nonce it minted.
  Nothing to configure: the entitlement and the App ID capability ride
  every build.
- A person who hides their email from you gets an Apple relay address
  (`…@privaterelay.appleid.com`) as their account email. For your app's
  own emails to reach it, register your sending domain under Sign in with
  Apple for Email Communication in Apple Developer → Services.

## Push notifications

Your backend has push built in, at parity with Base44's:

- Your code sends with `base44.asServiceRole.integrations.Core.SendPushNotification({
  user_id, title, content, action_label, action_url })` from a backend
  function — one person per call, up to 100 characters of title and 500 of
  content, an optional page of your app to open on tap. (An app that had no
  backend functions when it was migrated turns them on first, in this same
  Push section of its EscapeBase44 page.)
- The app registers each signed-in person's device the moment push is set
  up for its platform — it never asks anyone for permission before that.
- **iPhone**: an APNs auth key (Apple Developer → Certificates, Identifiers &
  Profiles → Keys → Apple Push Notifications service), pasted on the card.
  No rebuild: the app already carries the push entitlement.
- **Android**: your Firebase project's service account key (Firebase →
  Project settings → Service accounts → Generate new private key), uploaded
  on the card, then one Android rebuild. Every Android build registers your
  package in that project when it is not there yet and reads its
  `google-services.json` from it (`mobile/firebase-config.mjs`).

## In-app purchases

Apple and Google require their own billing (StoreKit / Play Billing) for
digital goods sold inside mobile apps. This repo ships with store billing
wired: your web code calls `window.eb44.iap` (injected into index.html),
the real store payment sheet opens, and your backend checks the purchase
with the store and records it on the signed-in person — the same on web and
app: buy on the phone, have it everywhere.

- **Subscriptions and one-time unlocks** — an entitlement on the person,
  read with `eb44.iap.hasEntitlement(id)` from web and app.
- **Credit packs** (bought again and again, used up in the app) — each
  pack adds a number to a number field of the person's own User record, once
  per purchase, the moment the store confirms it. Declare the packs in
  `.escapebase44/config.json` → `env`, as product = field + amount:

  ```
  "IAP_CREDIT_PACKS": "credits_100=credits+100, credits_500=credits+500"
  ```

  (the card writes it for you). Make them **Consumable** in App Store
  Connect, and plain in-app products in Play Console. A purchase of a pack
  not declared is never lost: on iPhone it waits, unfinished, until you
  declare it; on Android Google refunds it after three days. A refunded pack
  takes its credits back.
- **Renewals, cancellations and refunds** reach your backend on their own.
  iPhone: the moment they happen — the iPhone build points your App Store
  record's server notifications at it (unless they go to a purchases service
  you use). Android: your backend reads Google's own record — a renewal when
  the purchase is next read, a refund within five minutes of the next read.
  Want Google to tell it the moment something changes? In Google Cloud, make
  a Pub/Sub topic (Google Play's publisher,
  `google-play-developer-notifications@system.gserviceaccount.com`, may
  publish to it) and a subscription that sends each message to
  `https://teachertranslate.eb44.app/api/apps/<your app id>/eb44/iap/google/notifications`, and name
  the topic in Play Console → Monetization setup.

1. **Create the products** — App Store Connect → Monetization → In-App
   Purchases / Subscriptions, and Play Console → Products. Use the same
   product id on both (e.g. `premium_monthly`). Apple sells nothing until
   the Paid Apps agreement is active (App Store Connect → Business: the
   agreement, your bank and your tax forms). Google subscriptions carry a
   "base plan" id — the `plan` value below.
2. **iPhone — nothing else.** Purchases arrive as Apple-signed transactions
   your backend verifies directly.
3. **Android — one credential.** Paste your Play service account's JSON key
   on the card (Google Cloud Console → Service Accounts; invite its email in
   Play Console → Users and permissions with "View financial data" +
   "Manage orders").
4. **Wire it into your app** — ask the builder:

   > Inside the mobile app (window.eb44.isMobileApp() is true), sell through window.eb44.iap instead of the web checkout:
   > window.eb44.iap.purchase("premium_monthly", { type: "subs", plan: "monthly" }) for the subscription, and window.eb44.iap.purchase("credits_100", { type: "consumable" }) for a credit pack, then re-read the user's credits.
   > Treat a user as paid when the existing web logic says so OR when window.eb44.iap.hasEntitlement("premium_monthly") resolves true.
   > Add a "Restore purchases" button in settings, shown only in the mobile app, that calls window.eb44.iap.restore().
   > In the mobile app, show the link to the web checkout only when (await window.eb44.iap.storefront()).webCheckoutLink is true, and keep the in-app purchase beside it.
   > Change nothing else.

The bridge (all methods return promises): `eb44.iap.available()`,
`getProducts([ids], {type})`, `purchase(id, {type: "inapp"|"subs"|"consumable", plan})`,
`restore()`, `entitlements()`, `hasEntitlement(id)`, `storefront()`.
Every launch hands your backend what the store still holds, so a purchase
interrupted by a dropped connection is delivered the next time the app opens.
Apple/Google take their commission (15–30%) on store purchases.

**Your web checkout inside the app**: on the App Store in the United States
an app may show a link to buy on its website beside the in-app purchase
(Apple's guideline 3.1.1(a)) — `storefront().webCheckoutLink` says when.
Everywhere else on the App Store, and on Google Play, the app must not show
or link to another way to pay for digital goods (on Google Play in the US,
only after joining Google's external content links program in Play Console,
and Google takes a fee on those sales). Physical goods and services keep
your normal checkout everywhere.

## Ads

`window.eb44.ads` shows Google's ads in the app (banners, full-screen,
rewarded), when the app has an **AdMob** app (admob.google.com — one app per
platform; its app id, `ca-app-pub-…~…`, goes on the card, which writes
`ADMOB_APP_ID_IOS` / `ADMOB_APP_ID_ANDROID` and the next build carries
Google's ads SDK). Ask the builder:

> Inside the mobile app, call window.eb44.ads.start() once at launch (it asks for consent where the law wants it, and on iPhone Apple's tracking question).
> Then window.eb44.ads.banner("<ad unit id>") on the screens that show a banner, window.eb44.ads.interstitial("<ad unit id>") between two screens, and window.eb44.ads.rewarded("<ad unit id>") for a reward the person chooses to watch for.
> Add a "Privacy options" item in settings that calls window.eb44.ads.privacyOptions().
> Pass { test: true } while testing.

Ads already in your pages (**AdSense**, Ad Manager) are allowed inside the
app too: every build that finds Google's ad tags in your app carries the
same SDK for them (Google's WebView API for Ads), with no AdMob app needed.
Your backend serves `app-ads.txt` from your app's address with the publisher
inside your AdMob app ids — add your app's address as its website on the
store listings so AdMob can find it.

## Review checklist (the known rejection causes, pre-empted)

- **Login**: your login page includes email/password — Apple rejects apps
  whose ONLY login is Google. Google sign-in opens in an in-app sheet and
  returns through `eb44-69fc81cf4f6a0ae5ab617e2b://`; nothing to configure.
- **Payments**: digital goods are sold through the store inside the app
  (see "Your web checkout inside the app" above). Physical goods and
  services keep your normal checkout.
- **Reviewer access**: a demo account in App Store Connect → App Review
  Information, so reviewers get past your login.
- **Listing**: privacy policy + support link + screenshots (iPhone only —
  the app is built for iPhone; iPad screenshots are not asked for).
- **Account deletion**: Apple asks for a way to delete your account inside
  any app people can sign up in (guideline 5.1.1). Ask the builder:

  > Add a "Delete my account" button to the settings page. It asks the
  > person to confirm, then calls base44.entities.User.delete(<the signed-in
  > user's id>) and signs them out.

- **Permissions**: the iPhone app says why it might use the camera,
  microphone, photo library and location (shown only when your app asks) —
  in general words unless you write your own in `mobile/native.json`
  (`ios.infoPlist`), which Apple prefers — and that it uses no encryption
  beyond HTTPS. The Android app declares location, camera and microphone
  only when your app's code uses them, and the permissions you add.
- **"Just a website" (guideline 4.2)**: native touches help — push notifications are one click away above; you own the code for the rest.

## What your app can do on a phone

Inside the app your pages do what they do in the phone's browser:

- **Location, camera, microphone** — the phone asks the person the first
  time your app does. On Android an app may only ask for what it declares,
  so every Android build reads your built web app and declares exactly what
  its code uses (the build log says what it found: `EB44 {"kind":
  "android-identity", … "location": true}`).
- **Downloads** — a file your app saves (a CSV or PDF export, any download
  link) opens the phone's own screen for it: the share sheet on iPhone (Save
  to Files, AirDrop, Mail, Print), the Save screen on Android.
- **Print** — `window.print()` opens the phone's print screen.
- **Share** — `navigator.share` opens the phone's share sheet.
- **Full screen** — a video's full-screen button (or the page's own
  `requestFullscreen`) fills the screen, and the phone turns to landscape.
- **Links to other sites, email and phone links** open in the phone's
  browser, mail app and dialer.

## Updating the app

The app loads your live deployed frontend (`server.url` in
`capacitor.config.json` — your app's permanent address, which keeps
working after you attach a custom domain), so web-code changes reach
installed apps through your normal deploy — no store resubmission. Store
updates are only needed when the native side changes (icon, plugins,
`mobile/native.json`, Android push setup, the first time your app uses location, the
camera or the microphone on Android): build again and submit the new build.
Prefer a fully-bundled app (works without loading from your server, but web
changes then require a store update)? Delete the `server` block and rebuild.

## When something stops

The success page reads every run and tells you what happened and what to
do. The same run is in this repo's Actions tab under **Mobile release**;
every stop prints an `EB44 {"code": …}` line there that the page turns
into words. EscapeBase44 is told about every failed build too.
