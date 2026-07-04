import "package:firebase_messaging/firebase_messaging.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";
import "package:sentry_flutter/sentry_flutter.dart";
import "package:supabase_flutter/supabase_flutter.dart";

import "../../app.dart";
import "../auth/profile_provider.dart";

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final firebaseOk = ref.watch(firebaseReadyProvider);
    final sentryOk = ref.watch(sentryEnabledProvider);
    final session = Supabase.instance.client.auth.currentSession;
    final profileAsync = ref.watch(userProfileProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text("DynamicRunner"),
        actions: [
          if (session != null)
            TextButton(
              onPressed: () async {
                await Supabase.instance.client.auth.signOut();
                if (context.mounted) context.go("/sign-in");
              },
              child: const Text("Sign out"),
            ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              "Phase 1 — signed in",
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            Text("Email: ${session?.user.email ?? "—"}"),
            Text("User id: ${session?.user.id ?? "—"}"),
            profileAsync.when(
              data: (profile) => Text(
                profile == null
                    ? "Profile row: not found for uid=${session?.user.id ?? '?'}\n(check debug console for details)"
                    : "Profile timezone: ${profile.timezone}, units: ${profile.units}",
              ),
              loading: () => const Text("Loading profile…"),
              error: (e, _) => Text("Profile error: $e"),
            ),
            Text("Firebase (FCM): ${firebaseOk ? "initialized" : "not initialized — add google-services.json"}"),
            Text("Sentry: ${sentryOk ? "enabled" : "disabled — set SENTRY_DSN to enable"}"),
            const Spacer(),
            FilledButton(
              onPressed: sentryOk
                  ? () async {
                      await Sentry.captureException(
                        StateError("DynamicRunner Sentry test event from HomeScreen"),
                        withScope: (scope) {
                          scope.setTag("source", "manual_test");
                        },
                      );
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text("Sent test error to Sentry."),
                          ),
                        );
                      }
                    }
                  : null,
              child: const Text("Send test event to Sentry"),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: firebaseOk
                  ? () async {
                      final messaging = FirebaseMessaging.instance;
                      await messaging.requestPermission();
                      final token = await messaging.getToken();
                      debugPrint("FCM token: $token");
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(
                              token == null ? "No FCM token" : "FCM token logged to console",
                            ),
                          ),
                        );
                      }
                    }
                  : null,
              child: const Text("Register FCM token (needs Firebase)"),
            ),
          ],
        ),
      ),
    );
  }
}
