import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:supabase_flutter/supabase_flutter.dart";

/// Row from `public.profiles` (after Phase 1.6 migrations are applied).
class UserProfile {
  const UserProfile({
    required this.userId,
    this.email,
    this.timezone = "UTC",
    this.units = "metric",
  });

  final String userId;
  final String? email;
  final String timezone;
  final String units;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      userId: json["user_id"] as String,
      email: json["email"] as String?,
      timezone: json["timezone"] as String? ?? "UTC",
      units: json["units"] as String? ?? "metric",
    );
  }
}

final userProfileProvider = FutureProvider<UserProfile?>((ref) async {
  final session = Supabase.instance.client.auth.currentSession;
  if (session == null) return null;

  try {
    final row = await Supabase.instance.client
        .from("profiles")
        .select("user_id, email, timezone, units")
        .eq("user_id", session.user.id)
        .maybeSingle();
    if (row == null) return null;
    return UserProfile.fromJson(row);
  } on PostgrestException catch (e) {
    // Table missing until migrations are applied.
    if (e.code == "PGRST205" || e.message.contains("profiles")) {
      return null;
    }
    rethrow;
  }
});
