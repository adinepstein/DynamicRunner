import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:supabase_flutter/supabase_flutter.dart";

import "../onboarding_provider.dart";

class ProfileCaptureStep extends ConsumerStatefulWidget {
  const ProfileCaptureStep({super.key});

  @override
  ConsumerState<ProfileCaptureStep> createState() => _ProfileCaptureStepState();
}

class _ProfileCaptureStepState extends ConsumerState<ProfileCaptureStep> {
  final _formKey = GlobalKey<FormState>();
  int? _age;
  String _sex = "male";
  double? _weightKg;
  String _injuries = "";
  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.person_outline, size: 64, color: Colors.teal),
              const SizedBox(height: 16),
              Text(
                "About you",
                style: Theme.of(context).textTheme.headlineSmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                "This helps us tailor your training plan safely.",
                style: Theme.of(context).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),

              TextFormField(
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: "Age",
                  suffixText: "years",
                ),
                validator: (v) {
                  final age = int.tryParse(v ?? "");
                  if (age == null || age < 13 || age > 100) return "Enter a valid age (13-100)";
                  return null;
                },
                onSaved: (v) => _age = int.tryParse(v ?? ""),
              ),
              const SizedBox(height: 16),

              DropdownButtonFormField<String>(
                initialValue: _sex,
                decoration: const InputDecoration(labelText: "Sex"),
                items: const [
                  DropdownMenuItem(value: "male", child: Text("Male")),
                  DropdownMenuItem(value: "female", child: Text("Female")),
                  DropdownMenuItem(value: "other", child: Text("Prefer not to say")),
                ],
                onChanged: (v) => setState(() => _sex = v ?? "male"),
              ),
              const SizedBox(height: 16),

              TextFormField(
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: "Weight",
                  suffixText: "kg",
                ),
                validator: (v) {
                  final w = double.tryParse(v ?? "");
                  if (w == null || w < 30 || w > 250) return "Enter a valid weight (30-250 kg)";
                  return null;
                },
                onSaved: (v) => _weightKg = double.tryParse(v ?? ""),
              ),
              const SizedBox(height: 16),

              TextFormField(
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: "Current injuries or limitations (optional)",
                  hintText: "e.g. left knee pain, recovering from shin splints",
                ),
                onSaved: (v) => _injuries = v ?? "",
              ),
              const SizedBox(height: 32),

              FilledButton(
                onPressed: _saving ? null : _save,
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
      ),
    );
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    _formKey.currentState!.save();

    setState(() => _saving = true);

    try {
      final client = Supabase.instance.client;
      final uid = client.auth.currentUser!.id;

      await client.from("profiles").update({
        "athlete_profile": {
          "age": _age,
          "sex": _sex,
          "weightKg": _weightKg,
          "injuries": _injuries,
        },
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
