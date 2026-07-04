import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:hive_flutter/hive_flutter.dart";

/// Onboarding steps in order.
enum OnboardingStep {
  connectGarmin, // Step 1: Link Garmin account
  backfillProgress, // Step 2: Wait for 90-day backfill
  profileCapture, // Step 3: Age, sex, weight, injuries
  raceGoal, // Step 4: Pick race event + goal
  trainingDays, // Step 5: Select available days + long run day
  review, // Step 6: Confirm and generate plan
}

/// Persisted onboarding state — survives app kill.
class OnboardingState {
  final OnboardingStep currentStep;
  final bool completed;

  const OnboardingState({
    this.currentStep = OnboardingStep.connectGarmin,
    this.completed = false,
  });

  OnboardingState copyWith({
    OnboardingStep? currentStep,
    bool? completed,
  }) {
    return OnboardingState(
      currentStep: currentStep ?? this.currentStep,
      completed: completed ?? this.completed,
    );
  }

  int get stepIndex => currentStep.index;
  int get totalSteps => OnboardingStep.values.length;
  double get progress => (stepIndex + 1) / totalSteps;
}

class OnboardingNotifier extends StateNotifier<OnboardingState> {
  OnboardingNotifier() : super(const OnboardingState()) {
    _loadFromHive();
  }

  static const _boxName = "onboarding";
  static const _stepKey = "current_step";
  static const _completedKey = "completed";

  Future<void> _loadFromHive() async {
    final box = await Hive.openBox(_boxName);
    final stepIndex = box.get(_stepKey, defaultValue: 0) as int;
    final completed = box.get(_completedKey, defaultValue: false) as bool;

    if (completed) {
      state = const OnboardingState(
        currentStep: OnboardingStep.review,
        completed: true,
      );
    } else if (stepIndex < OnboardingStep.values.length) {
      state = OnboardingState(
        currentStep: OnboardingStep.values[stepIndex],
      );
    }
  }

  Future<void> _persist() async {
    final box = await Hive.openBox(_boxName);
    await box.put(_stepKey, state.currentStep.index);
    await box.put(_completedKey, state.completed);
  }

  void goToStep(OnboardingStep step) {
    state = state.copyWith(currentStep: step);
    _persist();
  }

  void nextStep() {
    final nextIndex = state.currentStep.index + 1;
    if (nextIndex >= OnboardingStep.values.length) {
      complete();
      return;
    }
    state = state.copyWith(currentStep: OnboardingStep.values[nextIndex]);
    _persist();
  }

  void previousStep() {
    final prevIndex = state.currentStep.index - 1;
    if (prevIndex < 0) return;
    state = state.copyWith(currentStep: OnboardingStep.values[prevIndex]);
    _persist();
  }

  void complete() {
    state = state.copyWith(completed: true);
    _persist();
  }

  Future<void> reset() async {
    state = const OnboardingState();
    final box = await Hive.openBox(_boxName);
    await box.clear();
  }
}

final onboardingProvider =
    StateNotifierProvider<OnboardingNotifier, OnboardingState>(
  (ref) => OnboardingNotifier(),
);

/// Whether the user needs onboarding (not completed yet).
final needsOnboardingProvider = Provider<bool>((ref) {
  final onboarding = ref.watch(onboardingProvider);
  return !onboarding.completed;
});
