import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../onboarding_provider.dart";
import "../../garmin/garmin_sync_provider.dart";
import "../../../services/api_client.dart";

class ConnectGarminStep extends ConsumerStatefulWidget {
  const ConnectGarminStep({super.key});

  @override
  ConsumerState<ConnectGarminStep> createState() => _ConnectGarminStepState();
}

class _ConnectGarminStepState extends ConsumerState<ConnectGarminStep> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _mfaController = TextEditingController();
  bool _loading = false;
  String? _error;
  bool _mfaRequired = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _mfaController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final syncStatus = ref.watch(garminSyncStatusProvider);

    return Padding(
      padding: const EdgeInsets.all(24),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.watch, size: 64, color: Colors.teal),
            const SizedBox(height: 16),
            Text(
              "Connect your Garmin",
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              "We'll import your training history to build a personalized plan.",
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),

            syncStatus.when(
              data: (status) {
                if (status.isConnected) {
                  return Column(
                    children: [
                      const Icon(Icons.check_circle, color: Colors.green, size: 48),
                      const SizedBox(height: 8),
                      Text("Connected as ${status.garminUserId ?? 'linked'}"),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: () => ref.read(onboardingProvider.notifier).nextStep(),
                        child: const Text("Continue"),
                      ),
                    ],
                  );
                }
                return const SizedBox.shrink();
              },
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
            ),

            if (!_mfaRequired) ...[
              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: "Garmin email",
                  prefixIcon: Icon(Icons.email_outlined),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passwordController,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "Garmin password",
                  prefixIcon: Icon(Icons.lock_outlined),
                ),
              ),
            ],

            if (_mfaRequired) ...[
              const SizedBox(height: 8),
              Text(
                "Enter the MFA code sent to your email or authenticator.",
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _mfaController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: "MFA code",
                  prefixIcon: Icon(Icons.security),
                ),
              ),
            ],

            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],

            const SizedBox(height: 24),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: _loading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_mfaRequired ? "Verify MFA" : "Connect Garmin"),
            ),

            const SizedBox(height: 12),
            TextButton(
              onPressed: () => ref.read(onboardingProvider.notifier).nextStep(),
              child: const Text("Skip for now"),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    final api = ref.read(apiClientProvider);

    try {
      if (_mfaRequired) {
        await _submitMfa(api);
      } else {
        await _submitLogin(api);
      }
    } catch (e) {
      setState(() => _error = "Network error: $e");
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitLogin(ApiClient api) async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (email.isEmpty || password.isEmpty) {
      setState(() => _error = "Please enter both email and password.");
      return;
    }

    final resp = await api.post("/garmin/login", body: {
      "email": email,
      "password": password,
    });

    if (!mounted) return;

    if (resp.isOk) {
      final status = resp.body["status"] as String?;
      if (status == "mfa_required") {
        setState(() => _mfaRequired = true);
      } else if (status == "connected") {
        _triggerBackfill(api);
        ref.read(onboardingProvider.notifier).nextStep();
      }
    } else {
      setState(() => _error = resp.errorMessage);
    }
  }

  Future<void> _submitMfa(ApiClient api) async {
    final code = _mfaController.text.trim();
    if (code.isEmpty) {
      setState(() => _error = "Please enter the MFA code.");
      return;
    }

    final resp = await api.post("/garmin/mfa", body: {"code": code});

    if (!mounted) return;

    if (resp.isOk) {
      _triggerBackfill(api);
      ref.read(onboardingProvider.notifier).nextStep();
    } else {
      setState(() => _error = resp.errorMessage);
    }
  }

  void _triggerBackfill(ApiClient api) {
    api.post("/garmin/backfill", body: {"days": 90});
  }
}
