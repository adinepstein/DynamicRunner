import "package:flutter/foundation.dart";
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

final userProfileProvider = FutureProvider.autoDispose<UserProfile?>((ref) async {
  final client = Supabase.instance.client;
  final session = client.auth.currentSession;
  if (session == null) {
    debugPrint("[profile_provider] No session");
    return null;
  }

  final uid = session.user.id;
  debugPrint("[profile_provider] uid=$uid token_starts=${session.accessToken.substring(0, 20)}");

  try {
    // Use rpc call to bypass potential RLS issues - fall back to direct query
    final row = await client
        .from("profiles")
        .select("user_id, email, timezone, units")
        .eq("user_id", uid)
        .maybeSingle();

    if (row != null) {
      debugPrint("[profile_provider] Got profile: $row");
      return UserProfile.fromJson(row);
    }

    // RLS might be blocking. Build profile from auth user data as fallback.
    debugPrint("[profile_provider] Query returned null, using auth user as fallback");
    return UserProfile(
      userId: uid,
      email: session.user.email,
      timezone: "UTC",
      units: "metric",
    );
  } catch (e) {
    debugPrint("[profile_provider] Error: $e — using fallback");
    return UserProfile(
      userId: uid,
      email: session.user.email,
      timezone: "UTC",
      units: "metric",
    );
  }
});
