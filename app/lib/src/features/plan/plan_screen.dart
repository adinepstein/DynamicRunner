import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "plan_provider.dart";
import "../../services/api_client.dart";

class PlanScreen extends ConsumerWidget {
  const PlanScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final planAsync = ref.watch(activePlanProvider);

    return Scaffold(
      appBar: AppBar(title: const Text("Training Plan")),
      body: planAsync.when(
        data: (plan) {
          if (plan == null) return const _NoPlanView();
          return _PlanDetailView(plan: plan);
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text("Error: $e")),
      ),
    );
  }
}

class _NoPlanView extends ConsumerWidget {
  const _NoPlanView();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.calendar_today, size: 64, color: Colors.grey),
            const SizedBox(height: 16),
            Text(
              "No active plan yet",
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            const Text(
              "Complete onboarding to generate your personalized training plan.",
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => _generatePlan(context, ref),
              icon: const Icon(Icons.auto_awesome),
              label: const Text("Generate Plan"),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _generatePlan(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiClientProvider);
    final resp = await api.post("/plan/generate");

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(resp.isOk
              ? "Plan generation started! Check back in 30-60 seconds."
              : resp.errorMessage),
        ),
      );
    }
  }
}

class _PlanDetailView extends StatelessWidget {
  final PlanSummary plan;
  const _PlanDetailView({required this.plan});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header card with methodology
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.emoji_events, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        _formatRaceType(plan.raceType ?? ""),
                        style: theme.textTheme.titleLarge,
                      ),
                    ],
                  ),
                  if (plan.raceDate != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      "Race date: ${plan.raceDate}",
                      style: theme.textTheme.bodyMedium,
                    ),
                  ],
                  const SizedBox(height: 12),
                  Chip(
                    label: Text(_formatMethodology(plan.methodology ?? "")),
                    avatar: const Icon(Icons.psychology, size: 18),
                  ),
                  if (plan.methodologyRationale != null) ...[
                    const SizedBox(height: 12),
                    ExpansionTile(
                      title: const Text("Why this approach?"),
                      tilePadding: EdgeInsets.zero,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Text(
                            plan.methodologyRationale!,
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Weekly structure
          Text("Weekly Overview", style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),

          if (plan.weeklyStructure.isNotEmpty)
            ...plan.weeklyStructure.map((week) => _WeekCard(week: week)),

          if (plan.weeklyStructure.isEmpty)
            const Text("Loading weekly structure..."),
        ],
      ),
    );
  }

  String _formatRaceType(String type) {
    const map = {
      "5k": "5K",
      "10k": "10K",
      "half_marathon": "Half Marathon",
      "marathon": "Marathon",
      "ultra": "Ultra",
    };
    return map[type] ?? type;
  }

  String _formatMethodology(String m) {
    const map = {
      "polarized_80_20": "Polarized 80/20",
      "daniels_vdot": "Daniels VDOT",
      "pfitzinger": "Pfitzinger",
      "hanson": "Hanson",
      "hybrid": "Hybrid",
    };
    return map[m] ?? m;
  }
}

class _WeekCard extends StatelessWidget {
  final WeekStructure week;
  const _WeekCard({required this.week});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: _phaseColor(week.phase),
          child: Text(
            week.isoWeek.split("-W").last,
            style: const TextStyle(fontSize: 12, color: Colors.white),
          ),
        ),
        title: Text("Week ${week.isoWeek.split('-W').last}"),
        subtitle: Text(
          [
            if (week.phase != null) week.phase!,
            if (week.targetVolumeKm != null) "${week.targetVolumeKm!.toStringAsFixed(0)} km",
            if (week.qualitySessions != null) "${week.qualitySessions} quality",
          ].join(" · "),
        ),
      ),
    );
  }

  Color _phaseColor(String? phase) {
    switch (phase) {
      case "base":
        return Colors.green;
      case "build":
        return Colors.orange;
      case "peak":
        return Colors.red;
      case "taper":
        return Colors.blue;
      case "recovery":
        return Colors.grey;
      default:
        return Colors.teal;
    }
  }
}
