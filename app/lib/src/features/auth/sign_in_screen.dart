import "package:flutter/material.dart";
import "package:go_router/go_router.dart";
import "package:supabase_flutter/supabase_flutter.dart";

enum _AuthAction { signIn, signUp }

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  _AuthAction? _pendingAction;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    _pendingAction = _AuthAction.signIn;
    await _runAuth(() => Supabase.instance.client.auth.signInWithPassword(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        ));
  }

  Future<void> _signUp() async {
    _pendingAction = _AuthAction.signUp;
    await _runAuth(() => Supabase.instance.client.auth.signUp(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        ));
  }

  Future<void> _runAuth(Future<AuthResponse> Function() call) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await call();
      if (!mounted) return;
      if (response.session == null) {
        setState(() {
          _error = "Check your email to confirm sign-up (or disable confirm email in Supabase Auth).";
        });
        return;
      }
      context.go("/");
    } on AuthException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _pendingAction = null;
        });
      }
    }
  }

  Widget _actionChild(_AuthAction action, String label) {
    if (_loading && _pendingAction == action) {
      return const SizedBox(
        height: 20,
        width: 20,
        child: CircularProgressIndicator(strokeWidth: 2),
      );
    }
    return Text(label);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Sign in")),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                "DynamicRunner",
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              const Text("Email and password (Google coming in a later step)."),
              const SizedBox(height: 24),
              TextField(
                controller: _emailController,
                decoration: const InputDecoration(
                  labelText: "Email",
                  border: OutlineInputBorder(),
                ),
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                autofillHints: const [AutofillHints.email],
                textInputAction: TextInputAction.next,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passwordController,
                decoration: const InputDecoration(
                  labelText: "Password",
                  border: OutlineInputBorder(),
                ),
                obscureText: true,
                autofillHints: const [AutofillHints.password],
                textInputAction: TextInputAction.done,
                onSubmitted: (_) {
                  if (!_loading) _signIn();
                },
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 32),
              FilledButton(
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: _loading ? null : _signIn,
                child: _actionChild(_AuthAction.signIn, "Sign in"),
              ),
              const SizedBox(height: 20),
              TextButton(
                style: TextButton.styleFrom(
                  minimumSize: const Size.fromHeight(44),
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                ),
                onPressed: _loading ? null : _signUp,
                child: _actionChild(_AuthAction.signUp, "Create account"),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
