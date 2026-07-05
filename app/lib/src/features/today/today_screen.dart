import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";
import "../plan/plan_provider.dart";

/// Provider for today's workout.
final todayWorkoutProvider = FutureProvider.autoDispose<PlannedWorkout?>((ref) async {
  final api = ref.read(apiClientProvider);
  final now = DateTime.now();
  final today = "${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}";

  final resp = await api.get("/plan/workouts?from_date=$today&to_date=$today");
  if (!resp.isOk) return null;

  final raw = resp.body["raw"];
  if (raw != null && raw is String) {
    try {
      final items = jsonDecode(raw) as List<dynamic>;
      if (items.isNotEmpty) {
        return PlannedWorkout.fromJson(items[0] as Map<String, dynamic>);
      }
    } catch (_) {}
  }
  return null;
});

class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final todayAsync = ref.watch(todayWorkoutProvider);

    return Scaffold(
      appBar: AppBar(title: const Text("Today")),
      body: todayAsync.when(
        data: (workout) {
          if (workout == null) return const _RestDayView();
          return _WorkoutHeroCard(workout: workout);
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text("Error: $e")),
      ),
    );
  }
}

class _RestDayView extends StatelessWidget {
  const _RestDayView();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.self_improvement, size: 80, color: Colors.teal),
            const SizedBox(height: 16),
            Text(
              "Rest Day",
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              "Recovery is when adaptation happens. Enjoy your day off!",
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ],
        ),
      ),
    );
  }
}

class _WorkoutHeroCard extends ConsumerWidget {
  final PlannedWorkout workout;
  const _WorkoutHeroCard({required this.workout});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Hero card
          Card(
            color: _typeColor(workout.type).withValues(alpha: 0.1),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(_typeIcon(workout.type), size: 32, color: _typeColor(workout.type)),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          workout.title,
                          style: theme.textTheme.titleLarge,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 12,
                    children: [
                      Chip(
                        avatar: const Icon(Icons.timer, size: 16),
                        label: Text(workout.durationFormatted),
                      ),
                      Chip(
                        avatar: const Icon(Icons.directions_run, size: 16),
                        label: Text(workout.type),
                      ),
                    ],
                  ),
                  if (workout.description != null) ...[
                    const SizedBox(height: 12),
                    Text(workout.description!, style: theme.textTheme.bodyMedium),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Structure breakdown
          if (workout.structure.isNotEmpty) ...[
            Text("Workout Structure", style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            _StructureView(structure: workout.structure),
          ],

          const SizedBox(height: 24),

          // Push to watch button
          FilledButton.icon(
            onPressed: () => _pushToWatch(context, ref),
            icon: const Icon(Icons.watch),
            label: const Text("Push to Garmin Watch"),
          ),
        ],
      ),
    );
  }

  Future<void> _pushToWatch(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiClientProvider);
    final resp = await api.post("/plan/push-workout", body: {"workout_id": workout.id});

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(resp.isOk
              ? "Workout pushed to your Garmin!"
              : "Push failed: ${resp.errorMessage}"),
        ),
      );
    }
  }

  Color _typeColor(String type) {
    switch (type) {
      case "easy":
      case "recovery":
        return Colors.green;
      case "long":
        return Colors.blue;
      case "tempo":
      case "threshold":
        return Colors.orange;
      case "intervals":
      case "fartlek":
        return Colors.red;
      case "hills":
        return Colors.brown;
      default:
        return Colors.teal;
    }
  }

  IconData _typeIcon(String type) {
    switch (type) {
      case "easy":
      case "recovery":
        return Icons.directions_walk;
      case "long":
        return Icons.landscape;
      case "tempo":
      case "threshold":
        return Icons.speed;
      case "intervals":
      case "fartlek":
        return Icons.flash_on;
      case "hills":
        return Icons.terrain;
      case "rest":
        return Icons.self_improvement;
      default:
        return Icons.directions_run;
    }
  }
}

class _StructureView extends StatelessWidget {
  final Map<String, dynamic> structure;
  const _StructureView({required this.structure});

  @override
  Widget build(BuildContext context) {
    final warmup = structure["warmup"] as Map<String, dynamic>?;
    final mainSteps = structure["mainSteps"] as List<dynamic>? ?? [];
    final cooldown = structure["cooldown"] as Map<String, dynamic>?;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (warmup != null) _StepTile(step: warmup, label: "Warmup"),
            for (int i = 0; i < mainSteps.length; i++)
              _buildMainStep(mainSteps[i] as Map<String, dynamic>, i + 1),
            if (cooldown != null) _StepTile(step: cooldown, label: "Cooldown"),
          ],
        ),
      ),
    );
  }

  Widget _buildMainStep(Map<String, dynamic> step, int index) {
    if (step["kind"] == "repeat") {
      final repeat = step["repeat"] as int? ?? 2;
      final steps = step["steps"] as List<dynamic>? ?? [];
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("  $repeat×", style: const TextStyle(fontWeight: FontWeight.bold)),
            for (final s in steps)
              Padding(
                padding: const EdgeInsets.only(left: 24),
                child: _StepTile(step: s as Map<String, dynamic>, label: ""),
              ),
          ],
        ),
      );
    }
    return _StepTile(step: step, label: "$index.");
  }
}

class _StepTile extends StatelessWidget {
  final Map<String, dynamic> step;
  final String label;
  const _StepTile({required this.step, required this.label});

  @override
  Widget build(BuildContext context) {
    final kind = step["kind"] as String? ?? "";
    String description;

    if (kind == "duration") {
      final secs = step["seconds"] as int? ?? 0;
      final mins = secs ~/ 60;
      description = "${mins}min";
    } else if (kind == "distance") {
      final meters = step["meters"] as int? ?? 0;
      description = meters >= 1000 ? "${(meters / 1000).toStringAsFixed(1)}km" : "${meters}m";
    } else {
      description = "until lap";
    }

    final target = step["target"] as Map<String, dynamic>?;
    String targetStr = "";
    if (target != null) {
      final targetKind = target["kind"] as String? ?? "";
      if (targetKind == "hrZone") {
        targetStr = " @ Zone ${target["zone"]}";
      } else if (targetKind == "pace") {
        final minPace = target["minSecPerKm"] as int? ?? 0;
        targetStr = " @ ${minPace ~/ 60}:${(minPace % 60).toString().padLeft(2, '0')}/km";
      }
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Text("$label $description$targetStr"),
    );
  }
}
