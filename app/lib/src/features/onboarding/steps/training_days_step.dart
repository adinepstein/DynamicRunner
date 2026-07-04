import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:supabase_flutter/supabase_flutter.dart";

import "../onboarding_provider.dart";

class TrainingDaysStep extends ConsumerStatefulWidget {
  const TrainingDaysStep({super.key});

  @override
  ConsumerState<TrainingDaysStep> createState() => _TrainingDaysStepState();
}

class _TrainingDaysStepState extends ConsumerState<TrainingDaysStep> {
  final Set<int> _selectedDays = {1, 3, 5}; // Mon, Wed, Fri default
  int _longRunDay = 6; // Saturday default
  bool _saving = false;

  static const _dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.calendar_month, size: 64, color: Colors.teal),
            const SizedBox(height: 16),
            Text(
              "Training days",
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              "Which days can you run? (Select 3-6 days)",
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),

            Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.center,
              children: List.generate(7, (i) {
                final dayNum = i + 1; // 1=Mon, 7=Sun
                final selected = _selectedDays.contains(dayNum);
                return FilterChip(
                  label: Text(_dayNames[i]),
                  selected: selected,
                  onSelected: (v) {
                    setState(() {
                      if (v) {
                        _selectedDays.add(dayNum);
                      } else {
                        _selectedDays.remove(dayNum);
                        if (_longRunDay == dayNum) {
                          _longRunDay = _selectedDays.isNotEmpty
                              ? _selectedDays.last
                              : 6;
                        }
                      }
                    });
                  },
                );
              }),
            ),
            const SizedBox(height: 24),

            Text(
              "Long run day:",
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: _selectedDays.map((d) {
                return ChoiceChip(
                  label: Text(_dayNames[d - 1]),
                  selected: _longRunDay == d,
                  onSelected: (v) {
                    if (v) setState(() => _longRunDay = d);
                  },
                );
              }).toList(),
            ),

            const SizedBox(height: 32),
            FilledButton(
              onPressed: _saving || _selectedDays.length < 3 ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text("Continue"),
            ),
            if (_selectedDays.length < 3)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  "Select at least 3 training days",
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                  textAlign: TextAlign.center,
                ),
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

      final existing = await client
          .from("profiles")
          .select("athlete_profile")
          .eq("user_id", uid)
          .single();

      final profile = Map<String, dynamic>.from(
        (existing["athlete_profile"] as Map<String, dynamic>?) ?? {},
      );
      profile["trainingDays"] = _selectedDays.toList()..sort();
      profile["longRunDay"] = _longRunDay;

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
