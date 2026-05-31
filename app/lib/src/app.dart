import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import "features/auth/sign_in_screen.dart";
import "features/home/home_screen.dart";

/// True after [Firebase.initializeApp] succeeds (needed for FCM).
final firebaseReadyProvider = Provider<bool>((ref) => false);

/// True when `SENTRY_DSN` was passed at build time and Sentry was initialized.
final sentryEnabledProvider = Provider<bool>((ref) => false);

final _rootNavigatorKey = GlobalKey<NavigatorState>();

final goRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: "/",
    redirect: (context, state) {
      final loggedIn = Supabase.instance.client.auth.currentSession != null;
      final onSignIn = state.matchedLocation == "/sign-in";
      if (!loggedIn && !onSignIn) return "/sign-in";
      if (loggedIn && onSignIn) return "/";
      return null;
    },
    routes: [
      GoRoute(
        path: "/sign-in",
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: "/",
        builder: (context, state) => const HomeScreen(),
      ),
    ],
  );
});

class DynamicRunnerApp extends ConsumerWidget {
  const DynamicRunnerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(goRouterProvider);
    return MaterialApp.router(
      title: "DynamicRunner",
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF0D9488)),
        useMaterial3: true,
      ),
      routerConfig: router,
    );
  }
}
