import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../onboarding_provider.dart";
import "../../garmin/garmin_sync_provider.dart";

class BackfillProgressStep extends ConsumerWidget {
  const BackfillProgressStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncStatus = ref.watch(garminSyncStatusProvider);

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Icon(Icons.cloud_download, size: 64, color: Colors.teal),
          const SizedBox(height: 16),
          Text(
            "Importing your data",
            style: Theme.of(context).textTheme.headlineSmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            "We're pulling 90 days of training history from Garmin Connect.",
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),

          syncStatus.when(
            data: (status) {
              final progress = status.backfillProgress;
              final percent = (progress?["percent"] as num?)?.toDouble() ?? 0;
              final statusText = progress?["status"] as String? ?? "waiting";

              if (statusText == "complete" || status.syncStatus == "ok") {
                return Column(
                  children: [
                    const Icon(Icons.check_circle, color: Colors.green, size: 48),
                    const SizedBox(height: 12),
                    const Text("Import complete!"),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: () => ref.read(onboardingProvider.notifier).nextStep(),
                      child: const Text("Continue"),
                    ),
                  ],
                );
              }

              return Column(
                children: [
                  LinearProgressIndicator(value: percent / 100),
                  const SizedBox(height: 12),
                  Text(
                    "${percent.toInt()}% — $statusText",
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (progress?["days_processed"] != null)
                    Text(
                      "${progress!["days_processed"]}/${progress["days_total"]} days",
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                ],
              );
            },
            loading: () => const CircularProgressIndicator(),
            error: (e, _) => Text("Error: $e"),
          ),

          const SizedBox(height: 24),
          TextButton(
            onPressed: () => ref.read(onboardingProvider.notifier).nextStep(),
            child: const Text("Skip (continue without full history)"),
          ),
        ],
      ),
    );
  }
}
