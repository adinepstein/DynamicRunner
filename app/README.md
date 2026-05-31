# DynamicRunner app

Flutter **Android** client (Phase 1+).

## Prerequisites

- [Flutter SDK](https://docs.flutter.dev/get-started/install) (stable channel)
- Android Studio / Xcode tooling as needed for devices

## First-time setup (generates `android/`, `ios/`, etc.)

This repo ships `pubspec.yaml` and `lib/` only. Generate platform folders once:

```bash
cd app
flutter create . --org app.dynamicrunner --project-name dynamicrunner
flutter pub get
```

## Configure secrets (do not commit)

Full Supabase walkthrough: [`docs/supabase-setup.md`](../docs/supabase-setup.md).

Pass at **build/run** time with `--dart-define` (recommended):

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon (public) key |
| `SENTRY_DSN` | Sentry DSN for crash/error reporting |
| `ALLOW_INSECURE_SSL` | `true` only for local dev if the emulator hits `certificate_verify_failed` (see below) |

### SSL / `certificate_verify_failed` on emulator

If sign-in fails with `HandshakeException: certificate_verify_failed`, your Mac may reach Supabase fine while the **emulator** does not trust the TLS chain (common with **corporate VPN/proxy**).

Try in order:

1. Disable VPN / corporate proxy and cold-reboot the emulator.
2. Run on a **physical Android device** (`flutter devices`, then `flutter run -d <device-id>`).
3. Emulator **Settings → Date & time** — turn on automatic date/time.
4. **Dev-only:** set `"ALLOW_INSECURE_SSL": "true"` in `dart_defines.json` and fully restart the app (debug builds only; never for production).

Example:

```bash
cp dart_defines.json.example dart_defines.json   # edit with your keys
flutter run --dart-define-from-file=dart_defines.json
```

Or inline:

```bash
flutter run \
  --dart-define=SUPABASE_URL=https://xxxx.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ... \
  --dart-define=SENTRY_DSN=https://...@.ingest.sentry.io/...
```

Defaults in `lib/main.dart` are placeholders until you override them.

## Firebase / FCM

1. Add Firebase Android app and download `google-services.json`.
2. Place it at `android/app/google-services.json` (path is gitignored).
3. Re-run the app; **Firebase initialize** should succeed and the **FCM token** button will enable.

Until then, Firebase init is caught and the UI shows Firebase as not initialized.

## Sentry test

On the home screen, tap **Send test event to Sentry**. With a valid `SENTRY_DSN`, the event should appear in your Sentry project.

## Generated JSON Schema models

After JSON Schema changes, regenerate Dart types into `lib/src/generated/models/`:

```bash
# from repo root
./shared/schemas/scripts/generate_dart_models.sh
```

Requires Node/`npx` and `quicktype`.
