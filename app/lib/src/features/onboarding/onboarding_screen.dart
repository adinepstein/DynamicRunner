import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "onboarding_provider.dart";
import "steps/connect_garmin_step.dart";
import "steps/backfill_progress_step.dart";
import "steps/profile_capture_step.dart";
import "steps/race_goal_step.dart";
import "steps/training_days_step.dart";
import "steps/review_step.dart";

class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final onboarding = ref.watch(onboardingProvider);
    final notifier = ref.read(onboardingProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text("Setup"),
        leading: onboarding.stepIndex > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: notifier.previousStep,
              )
            : null,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Text(
                "Step ${onboarding.stepIndex + 1} of ${onboarding.totalSteps}",
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          LinearProgressIndicator(
            value: onboarding.progress,
            minHeight: 4,
          ),
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: _buildStep(onboarding.currentStep),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStep(OnboardingStep step) {
    switch (step) {
      case OnboardingStep.connectGarmin:
        return const ConnectGarminStep(key: ValueKey("garmin"));
      case OnboardingStep.backfillProgress:
        return const BackfillProgressStep(key: ValueKey("backfill"));
      case OnboardingStep.profileCapture:
        return const ProfileCaptureStep(key: ValueKey("profile"));
      case OnboardingStep.raceGoal:
        return const RaceGoalStep(key: ValueKey("race"));
      case OnboardingStep.trainingDays:
        return const TrainingDaysStep(key: ValueKey("days"));
      case OnboardingStep.review:
        return const ReviewStep(key: ValueKey("review"));
    }
  }
}
