import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:supabase_flutter/supabase_flutter.dart";

import "../onboarding_provider.dart";

class RaceGoalStep extends ConsumerStatefulWidget {
  const RaceGoalStep({super.key});

  @override
  ConsumerState<RaceGoalStep> createState() => _RaceGoalStepState();
}

class _RaceGoalStepState extends ConsumerState<RaceGoalStep> {
  String _raceDistance = "half_marathon";
  DateTime? _raceDate;
  final _eventNameController = TextEditingController();
  final _goalPaceController = TextEditingController();
  bool _saving = false;

  static const _distances = {
    "5k": "5K",
    "10k": "10K",
    "half_marathon": "Half Marathon",
    "marathon": "Marathon",
    "ultra": "Ultra (50K+)",
  };

  @override
  void dispose() {
    _eventNameController.dispose();
    _goalPaceController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final minDate = DateTime.now().add(const Duration(days: 28));

    return Padding(
      padding: const EdgeInsets.all(24),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.flag, size: 64, color: Colors.teal),
            const SizedBox(height: 16),
            Text(
              "Your race goal",
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              "We'll build a plan that peaks for your target race.",
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),

            TextField(
              controller: _eventNameController,
              decoration: const InputDecoration(
                labelText: "Event name (optional)",
                hintText: "e.g. Tel Aviv Marathon 2027",
              ),
            ),
            const SizedBox(height: 16),

            DropdownButtonFormField<String>(
              initialValue: _raceDistance,
              decoration: const InputDecoration(labelText: "Race distance"),
              items: _distances.entries
                  .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                  .toList(),
              onChanged: (v) => setState(() => _raceDistance = v ?? "half_marathon"),
            ),
            const SizedBox(height: 16),

            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                _raceDate == null
                    ? "Pick race date (at least 4 weeks out)"
                    : "Race date: ${_raceDate!.day}/${_raceDate!.month}/${_raceDate!.year}",
              ),
              trailing: const Icon(Icons.calendar_today),
              onTap: () async {
                final picked = await showDatePicker(
                  context: context,
                  initialDate: minDate,
                  firstDate: minDate,
                  lastDate: DateTime.now().add(const Duration(days: 365)),
                );
                if (picked != null) setState(() => _raceDate = picked);
              },
            ),
            const SizedBox(height: 16),

            TextField(
              controller: _goalPaceController,
              keyboardType: TextInputType.text,
              decoration: const InputDecoration(
                labelText: "Goal pace (optional)",
                hintText: "e.g. 5:30/km",
                helperText: "Leave empty to use Garmin race predictor estimate",
              ),
            ),
            const SizedBox(height: 32),

            FilledButton(
              onPressed: _saving || _raceDate == null ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text("Continue"),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    setState(() => _saving = true);

    try {
      final client = Supabase.instance.client;
      final uid = client.auth.currentUser!.id;

      // Read existing athlete_profile and merge race goal
      final existing = await client
          .from("profiles")
          .select("athlete_profile")
          .eq("user_id", uid)
          .single();

      final profile = Map<String, dynamic>.from(
        (existing["athlete_profile"] as Map<String, dynamic>?) ?? {},
      );
      profile["raceGoal"] = {
        "distance": _raceDistance,
        "date": _raceDate!.toIso8601String().split("T").first,
        "eventName": _eventNameController.text.trim(),
        "goalPace": _goalPaceController.text.trim(),
      };

      await client.from("profiles").update({
        "athlete_profile": profile,
      }).eq("user_id", uid);

      if (mounted) {
        ref.read(onboardingProvider.notifier).nextStep();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Save failed: $e")),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}
