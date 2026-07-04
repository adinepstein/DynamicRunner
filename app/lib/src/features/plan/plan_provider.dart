import "dart:convert";

import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class PlanSummary {
  final String id;
  final String status;
  final String? raceType;
  final String? raceDate;
  final String? methodology;
  final String? methodologyRationale;
  final List<WeekStructure> weeklyStructure;
  final String createdAt;

  PlanSummary({
    required this.id,
    required this.status,
    this.raceType,
    this.raceDate,
    this.methodology,
    this.methodologyRationale,
    this.weeklyStructure = const [],
    required this.createdAt,
  });

  factory PlanSummary.fromJson(Map<String, dynamic> json) {
    final payload = json["payload"] as Map<String, dynamic>? ?? {};
    final weeks = (payload["weeklyStructure"] as List<dynamic>? ?? [])
        .map((w) => WeekStructure.fromJson(w as Map<String, dynamic>))
        .toList();

    return PlanSummary(
      id: json["id"] as String,
      status: json["status"] as String,
      raceType: payload["raceType"] as String?,
      raceDate: payload["raceDate"] as String?,
      methodology: payload["methodology"] as String?,
      methodologyRationale: payload["methodologyRationale"] as String?,
      weeklyStructure: weeks,
      createdAt: json["created_at"] as String,
    );
  }
}

class WeekStructure {
  final String isoWeek;
  final String? phase;
  final double? targetVolumeKm;
  final int? qualitySessions;

  WeekStructure({
    required this.isoWeek,
    this.phase,
    this.targetVolumeKm,
    this.qualitySessions,
  });

  factory WeekStructure.fromJson(Map<String, dynamic> json) {
    return WeekStructure(
      isoWeek: json["isoWeek"] as String? ?? "",
      phase: json["phase"] as String?,
      targetVolumeKm: (json["targetVolumeKm"] as num?)?.toDouble(),
      qualitySessions: json["qualitySessions"] as int?,
    );
  }
}

class PlannedWorkout {
  final String id;
  final String scheduledDate;
  final String type;
  final String title;
  final String? description;
  final int estimatedDurationSec;
  final Map<String, dynamic> structure;
  final Map<String, dynamic>? targets;

  PlannedWorkout({
    required this.id,
    required this.scheduledDate,
    required this.type,
    required this.title,
    this.description,
    required this.estimatedDurationSec,
    required this.structure,
    this.targets,
  });

  factory PlannedWorkout.fromJson(Map<String, dynamic> json) {
    final payload = json["payload"] as Map<String, dynamic>? ?? {};
    return PlannedWorkout(
      id: json["id"] as String,
      scheduledDate: payload["scheduledDate"] as String? ?? json["scheduled_date"] as String,
      type: payload["type"] as String? ?? "easy",
      title: payload["title"] as String? ?? "Workout",
      description: payload["description"] as String?,
      estimatedDurationSec: payload["estimatedDurationSec"] as int? ?? 0,
      structure: payload["structure"] as Map<String, dynamic>? ?? {},
      targets: payload["targets"] as Map<String, dynamic>?,
    );
  }

  String get durationFormatted {
    final minutes = estimatedDurationSec ~/ 60;
    if (minutes >= 60) {
      final h = minutes ~/ 60;
      final m = minutes % 60;
      return "${h}h ${m}m";
    }
    return "${minutes}m";
  }

  bool get isRest => type == "rest";
}

/// Provider for the active plan.
final activePlanProvider = FutureProvider.autoDispose<PlanSummary?>((ref) async {
  final api = ref.read(apiClientProvider);
  final resp = await api.get("/plan/active");
  if (!resp.isOk || resp.body.containsKey("raw")) return null;
  return PlanSummary.fromJson(resp.body);
});

/// Provider for workouts of a given week.
final weekWorkoutsProvider = FutureProvider.autoDispose
    .family<List<PlannedWorkout>, String>((ref, weekStartDate) async {
  final api = ref.read(apiClientProvider);
  // Calculate end of week (7 days from start)
  final start = DateTime.parse(weekStartDate);
  final end = start.add(const Duration(days: 6));
  final endStr = "${end.year}-${end.month.toString().padLeft(2, '0')}-${end.day.toString().padLeft(2, '0')}";

  final resp = await api.get("/plan/workouts?from_date=$weekStartDate&to_date=$endStr");
  if (!resp.isOk) return [];

  // The response is a list
  final body = resp.body;
  if (body.containsKey("raw")) {
    // Try parsing raw as JSON list
    try {
      final list = jsonDecode(body["raw"] as String) as List<dynamic>;
      return list.map((w) => PlannedWorkout.fromJson(w as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  return [];
});
