import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class PlanProgress {
  final bool hasPlan;
  final String? raceType;
  final String? raceDate;
  final int totalWorkouts;
  final int completed;
  final int skipped;
  final int completionPct;
  final int totalWeeks;
  final int weeksElapsed;

  PlanProgress({
    required this.hasPlan,
    this.raceType,
    this.raceDate,
    this.totalWorkouts = 0,
    this.completed = 0,
    this.skipped = 0,
    this.completionPct = 0,
    this.totalWeeks = 0,
    this.weeksElapsed = 0,
  });

  factory PlanProgress.fromJson(Map<String, dynamic> json) {
    return PlanProgress(
      hasPlan: json["has_plan"] as bool? ?? false,
      raceType: json["race_type"] as String?,
      raceDate: json["race_date"] as String?,
      totalWorkouts: json["total_workouts"] as int? ?? 0,
      completed: json["completed"] as int? ?? 0,
      skipped: json["skipped"] as int? ?? 0,
      completionPct: json["completion_pct"] as int? ?? 0,
      totalWeeks: json["total_weeks"] as int? ?? 0,
      weeksElapsed: json["weeks_elapsed"] as int? ?? 0,
    );
  }
}

final planProgressProvider = FutureProvider.autoDispose<PlanProgress>((ref) async {
  final api = ref.read(apiClientProvider);
  final resp = await api.get("/dashboard/progress");
  if (!resp.isOk) return PlanProgress(hasPlan: false);

  final body = resp.body;
  if (body["has_plan"] != null) {
    return PlanProgress.fromJson(body);
  } else if (body["raw"] is String) {
    final decoded = jsonDecode(body["raw"] as String) as Map<String, dynamic>;
    return PlanProgress.fromJson(decoded);
  }
  return PlanProgress(hasPlan: false);
});

class PlanProgressWidget extends ConsumerWidget {
  const PlanProgressWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final progressAsync = ref.watch(planProgressProvider);

    return progressAsync.when(
      data: (progress) {
        if (!progress.hasPlan) {
          return const SizedBox.shrink();
        }
        return _ProgressCard(progress: progress);
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  final PlanProgress progress;
  const _ProgressCard({required this.progress});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final weeksRemaining = progress.totalWeeks - progress.weeksElapsed;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.flag, size: 20, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  progress.raceType ?? "Training Plan",
                  style: theme.textTheme.titleSmall,
                ),
                if (progress.raceDate != null) ...[
                  const Spacer(),
                  Text(progress.raceDate!, style: theme.textTheme.bodySmall),
                ],
              ],
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: progress.completionPct / 100,
                minHeight: 8,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  "${progress.completionPct}% complete",
                  style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                Text(
                  "Week ${progress.weeksElapsed}/${progress.totalWeeks}"
                  "${weeksRemaining > 0 ? ' ($weeksRemaining to go)' : ''}",
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              "${progress.completed} done · ${progress.skipped} skipped",
              style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
