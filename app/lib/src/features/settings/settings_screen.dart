import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";
import "package:supabase_flutter/supabase_flutter.dart";

import "../../services/api_client.dart";

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  bool _morningBriefing = true;
  bool _missedReminders = true;
  bool _weeklyReview = true;
  String _units = "metric";

  @override
  Widget build(BuildContext context) {
    final user = Supabase.instance.client.auth.currentUser;

    return Scaffold(
      appBar: AppBar(title: const Text("Settings")),
      body: ListView(
        children: [
          _SectionHeader(title: "Account"),
          ListTile(
            leading: const Icon(Icons.person),
            title: const Text("Email"),
            subtitle: Text(user?.email ?? "—"),
          ),
          const Divider(),

          _SectionHeader(title: "Garmin Connection"),
          ListTile(
            leading: const Icon(Icons.watch),
            title: const Text("Garmin Connect"),
            subtitle: const Text("Connected"),
            trailing: TextButton(
              onPressed: _disconnectGarmin,
              child: const Text("Disconnect", style: TextStyle(color: Colors.red)),
            ),
          ),
          const Divider(),

          _SectionHeader(title: "Notifications"),
          SwitchListTile(
            title: const Text("Morning briefing (06:30)"),
            subtitle: const Text("Daily workout preview"),
            value: _morningBriefing,
            onChanged: (v) => setState(() => _morningBriefing = v),
          ),
          SwitchListTile(
            title: const Text("Missed workout reminders"),
            value: _missedReminders,
            onChanged: (v) => setState(() => _missedReminders = v),
          ),
          SwitchListTile(
            title: const Text("Weekly review summary"),
            subtitle: const Text("Saturday evening"),
            value: _weeklyReview,
            onChanged: (v) => setState(() => _weeklyReview = v),
          ),
          const Divider(),

          _SectionHeader(title: "Preferences"),
          ListTile(
            title: const Text("Units"),
            trailing: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: "metric", label: Text("km")),
                ButtonSegment(value: "imperial", label: Text("mi")),
              ],
              selected: {_units},
              onSelectionChanged: (s) => setState(() => _units = s.first),
            ),
          ),
          const Divider(),

          _SectionHeader(title: "Danger Zone"),
          ListTile(
            leading: const Icon(Icons.delete_forever, color: Colors.red),
            title: const Text("Delete Account", style: TextStyle(color: Colors.red)),
            subtitle: const Text("Permanently delete all your data"),
            onTap: _confirmDelete,
          ),
        ],
      ),
    );
  }

  Future<void> _disconnectGarmin() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Disconnect Garmin?"),
        content: const Text("Your synced data will be preserved. You can reconnect anytime."),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Cancel")),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text("Disconnect")),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    final api = ref.read(apiClientProvider);
    await api.delete("/garmin?delete_data=false");

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Garmin disconnected")),
      );
    }
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Delete Account?"),
        content: const Text(
          "This will permanently delete your account and all associated data. "
          "This action cannot be undone.",
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Cancel")),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Delete", style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    final api = ref.read(apiClientProvider);
    await api.delete("/garmin?delete_data=true");
    await Supabase.instance.client.auth.signOut();

    if (mounted) {
      context.go("/sign-in");
    }
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleSmall?.copyWith(
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }
}
