# Mutowei Investments Android

Native Android companion for the existing Mutowei Investments desktop application.

## First milestone: Stock Foundation
- Premium midnight-navy and champagne-gold visual system.
- Bottom navigation: Home, Stock, Sales, Records, Account.
- Three independent shops: Mutowei Bottle Store, Bizzy Tuckshop, Chikofa Tuckshop.
- Local Room database foundation for offline-first records.
- Stock-first workflow; sales, records and account screens are initial navigation placeholders.

## Important integration boundary
The desktop app currently uses SQLite locally and Supabase **manual snapshot backup/restore per shop**. It does not provide live multi-device synchronization or a shared transaction API. This Android starter deliberately does not pretend otherwise, does not upload anything, and contains no Supabase credentials. A safe shared-data integration requires an explicit backend design/migration that preserves desktop data and adds idempotent movement-level synchronization. Do not point this app at production data until that is implemented and tested.

## Build
Open the `android/` directory in Android Studio (Giraffe or newer), allow Gradle sync, then run the `app` configuration on an Android device/emulator.

Minimum SDK: 26. Package: `zw.co.mutowei.app`.

## Current status
This is the first source-code foundation and UI preview, not a signed APK. Product cards currently use clearly marked preview data; Room entities/DAO/database are scaffolded but not yet wired to screens. No live Supabase connection is configured.

## Automated APK builds

GitHub Actions builds a debug APK for this branch. Open the repository Actions tab and download the `mutowei-investments-debug-apk` artifact after a successful run. This is a development build and is not yet connected to live shop records.
