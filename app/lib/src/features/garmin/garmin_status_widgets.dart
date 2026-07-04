import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'garmin_sync_provider.dart';

/// Banner shown when Garmin re-authentication is required.
class GarminReauthBanner extends ConsumerWidget {
  final VoidCallback? onReconnect;

  const GarminReauthBanner({super.key, this.onReconnect});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(garminSyncStatusProvider);

    return statusAsync.when(
      data: (status) {
        if (!status.needsReauth) return const SizedBox.shrink();
        return MaterialBanner(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          content: const Text(
            "Garmin connection expired. Reconnect to resume syncing.",
          ),
          leading: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          actions: [
            TextButton(
              onPressed: onReconnect,
              child: const Text("Reconnect"),
            ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }
}

/// Small status chip showing current Garmin sync state.
class GarminSyncChip extends ConsumerWidget {
  const GarminSyncChip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(garminSyncStatusProvider);

    return statusAsync.when(
      data: (status) {
        if (!status.isConnected) {
          return const Chip(
            avatar: Icon(Icons.link_off, size: 16),
            label: Text("Garmin not linked"),
          );
        }
        if (status.needsReauth) {
          return const Chip(
            avatar: Icon(Icons.error_outline, size: 16, color: Colors.orange),
            label: Text("Reconnect needed"),
          );
        }
        if (status.isSyncing) {
          return const Chip(
            avatar: SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            label: Text("Syncing..."),
          );
        }
        return Chip(
          avatar: const Icon(Icons.check_circle_outline, size: 16, color: Colors.green),
          label: Text("Garmin: ${status.garminUserId ?? "linked"}"),
        );
      },
      loading: () => const Chip(label: Text("Loading...")),
      error: (_, __) => const Chip(label: Text("Error")),
    );
  }
}
