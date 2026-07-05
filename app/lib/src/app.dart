import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import "features/auth/sign_in_screen.dart";
import "features/home/home_screen.dart";
import "features/onboarding/onboarding_provider.dart";
import "features/onboarding/onboarding_screen.dart";
import "features/plan/plan_screen.dart";
import "features/today/today_screen.dart";
import "features/adaptation/adaptation_feed_screen.dart";
import "features/adaptation/edit_week_screen.dart";
import "features/dashboard/dashboard_screen.dart";
import "features/settings/settings_screen.dart";

/// True after [Firebase.initializeApp] succeeds (needed for FCM).
final firebaseReadyProvider = Provider<bool>((ref) => false);

/// True when `SENTRY_DSN` was passed at build time and Sentry was initialized.
final sentryEnabledProvider = Provider<bool>((ref) => false);

final _rootNavigatorKey = GlobalKey<NavigatorState>();

final goRouterProvider = Provider<GoRouter>((ref) {
  final needsOnboarding = ref.watch(needsOnboardingProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: "/",
    redirect: (context, state) {
      final loggedIn = Supabase.instance.client.auth.currentSession != null;
      final onSignIn = state.matchedLocation == "/sign-in";
      final onOnboarding = state.matchedLocation == "/onboarding";

      if (!loggedIn && !onSignIn) return "/sign-in";
      if (loggedIn && onSignIn) return "/";
      if (loggedIn && needsOnboarding && !onOnboarding) return "/onboarding";
      if (loggedIn && !needsOnboarding && onOnboarding) return "/";
      return null;
    },
    routes: [
      GoRoute(
        path: "/sign-in",
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: "/onboarding",
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(
        path: "/",
        builder: (context, state) => const HomeScreen(),
      ),
      GoRoute(
        path: "/plan",
        builder: (context, state) => const PlanScreen(),
      ),
      GoRoute(
        path: "/today",
        builder: (context, state) => const TodayScreen(),
      ),
      GoRoute(
        path: "/changes",
        builder: (context, state) => const AdaptationFeedScreen(),
      ),
      GoRoute(
        path: "/edit-week",
        builder: (context, state) => const EditWeekScreen(),
      ),
      GoRoute(
        path: "/dashboard",
        builder: (context, state) => const DashboardScreen(),
      ),
      GoRoute(
        path: "/settings",
        builder: (context, state) => const SettingsScreen(),
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
