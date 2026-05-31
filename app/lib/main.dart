import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'src/app.dart';
import 'src/dev_ssl_override.dart';

/// Build-time overrides (run with `--dart-define=KEY=value`).
const _kSupabaseUrl = String.fromEnvironment(
  "SUPABASE_URL",
  defaultValue: "https://YOUR_PROJECT.supabase.co",
);
const _kSupabaseAnonKey = String.fromEnvironment(
  "SUPABASE_ANON_KEY",
  defaultValue: "YOUR_SUPABASE_ANON_KEY",
);
const _kSentryDsn = String.fromEnvironment("SENTRY_DSN", defaultValue: "");
const _kAllowInsecureSsl = bool.fromEnvironment("ALLOW_INSECURE_SSL", defaultValue: false);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (kDebugMode && _kAllowInsecureSsl) {
    HttpOverrides.global = DevSslHttpOverrides();
    debugPrint(
      "WARNING: ALLOW_INSECURE_SSL=true — TLS verification disabled (local dev only).",
    );
  }

  await Hive.initFlutter();

  await Supabase.initialize(
    url: _kSupabaseUrl,
    anonKey: _kSupabaseAnonKey,
  );

  var firebaseOk = false;
  try {
    await Firebase.initializeApp();
    firebaseOk = true;
  } catch (e, st) {
    debugPrint(
      "Firebase init skipped or failed (add android/app/google-services.json for FCM): $e\n$st",
    );
  }

  final sentryEnabled = _kSentryDsn.isNotEmpty;
  void runDynamicRunner() {
    runApp(
      ProviderScope(
        overrides: [
          firebaseReadyProvider.overrideWithValue(firebaseOk),
          sentryEnabledProvider.overrideWithValue(sentryEnabled),
        ],
        child: const DynamicRunnerApp(),
      ),
    );
  }

  if (sentryEnabled) {
    await SentryFlutter.init(
      (options) {
        options.dsn = _kSentryDsn;
        options.tracesSampleRate = 1.0;
      },
      appRunner: runDynamicRunner,
    );
  } else {
    runDynamicRunner();
  }
}
