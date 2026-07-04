import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Garmin connection status from garmin_profiles table.
class GarminSyncStatus {
  final String syncStatus;
  final bool reauthRequired;
  final String? garminUserId;
  final Map<String, dynamic>? backfillProgress;
  final DateTime? lastSyncAt;

  const GarminSyncStatus({
    required this.syncStatus,
    required this.reauthRequired,
    this.garminUserId,
    this.backfillProgress,
    this.lastSyncAt,
  });

  bool get isConnected => syncStatus != "disconnected";
  bool get isSyncing => syncStatus == "syncing";
  bool get needsReauth => reauthRequired;

  factory GarminSyncStatus.disconnected() => const GarminSyncStatus(
        syncStatus: "disconnected",
        reauthRequired: false,
      );

  factory GarminSyncStatus.fromRow(Map<String, dynamic> row) {
    return GarminSyncStatus(
      syncStatus: row["sync_status"] as String? ?? "disconnected",
      reauthRequired: row["reauth_required"] as bool? ?? false,
      garminUserId: row["garmin_user_id"] as String?,
      backfillProgress: row["backfill_progress"] as Map<String, dynamic>?,
      lastSyncAt: row["last_sync_at"] != null
          ? DateTime.tryParse(row["last_sync_at"] as String)
          : null,
    );
  }
}

/// Watches garmin_profiles via Supabase Realtime for live sync status updates.
final garminSyncStatusProvider =
    StreamProvider.autoDispose<GarminSyncStatus>((ref) {
  final client = Supabase.instance.client;
  final user = client.auth.currentUser;
  if (user == null) {
    return Stream.value(GarminSyncStatus.disconnected());
  }

  final controller = StreamController<GarminSyncStatus>();

  // Initial fetch
  client
      .from("garmin_profiles")
      .select()
      .eq("user_id", user.id)
      .maybeSingle()
      .then((row) {
    if (row == null) {
      controller.add(GarminSyncStatus.disconnected());
    } else {
      controller.add(GarminSyncStatus.fromRow(row));
    }
  }).catchError((e) {
    controller.add(GarminSyncStatus.disconnected());
  });

  // Subscribe to realtime changes
  final channel = client
      .channel("garmin_profiles_${user.id}")
      .onPostgresChanges(
        event: PostgresChangeEvent.all,
        schema: "public",
        table: "garmin_profiles",
        filter: PostgresChangeFilter(
          type: PostgresChangeFilterType.eq,
          column: "user_id",
          value: user.id,
        ),
        callback: (payload) {
          final newRow = payload.newRecord;
          if (newRow.isNotEmpty) {
            controller.add(GarminSyncStatus.fromRow(newRow));
          }
        },
      )
      .subscribe();

  ref.onDispose(() {
    client.removeChannel(channel);
    controller.close();
  });

  return controller.stream;
});
