import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";

import "../onboarding_provider.dart";

class ReviewStep extends ConsumerWidget {
  const ReviewStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Icon(Icons.celebration, size: 64, color: Colors.teal),
          const SizedBox(height: 16),
          Text(
            "You're all set!",
            style: Theme.of(context).textTheme.headlineSmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            "We'll generate your personalized training plan based on your history, goals, and available days.",
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          FilledButton.icon(
            onPressed: () {
              ref.read(onboardingProvider.notifier).complete();
              context.go("/");
            },
            icon: const Icon(Icons.rocket_launch),
            label: const Text("Generate my plan"),
          ),
        ],
      ),
    );
  }
}
