import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class AdaptationEntry {
  final String id;
  final String agentType;
  final String? summary;
  final List<String> rules;
  final bool success;
  final String createdAt;

  AdaptationEntry({
    required this.id,
    required this.agentType,
    this.summary,
    this.rules = const [],
    required this.success,
    required this.createdAt,
  });

  factory AdaptationEntry.fromJson(Map<String, dynamic> json) {
    final payload = json["payload"] as Map<String, dynamic>? ?? {};
    return AdaptationEntry(
      id: json["id"] as String,
      agentType: payload["agent_type"] as String? ?? "unknown",
      summary: payload["summary"] as String?,
      rules: (payload["rules"] as List<dynamic>?)?.cast<String>() ?? [],
      success: payload["success"] as bool? ?? true,
      createdAt: json["created_at"] as String,
    );
  }
}

/// Provider for the adaptation history feed.
final adaptationFeedProvider = FutureProvider.autoDispose<List<AdaptationEntry>>((ref) async {
  final api = ref.read(apiClientProvider);
  final resp = await api.get("/adaptation/feed");
  if (!resp.isOk) return [];

  final raw = resp.body["raw"];
  if (raw != null && raw is String) {
    try {
      final items = jsonDecode(raw) as List<dynamic>;
      return items
          .map((e) => AdaptationEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
  }
  return [];
});

class AdaptationFeedScreen extends ConsumerWidget {
  const AdaptationFeedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feedAsync = ref.watch(adaptationFeedProvider);

    return Scaffold(
      appBar: AppBar(title: const Text("What Changed")),
      body: feedAsync.when(
        data: (entries) {
          if (entries.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.check_circle_outline, size: 64, color: Colors.green),
                    SizedBox(height: 16),
                    Text("No changes yet", style: TextStyle(fontSize: 18)),
                    SizedBox(height: 8),
                    Text(
                      "Your plan adjustments will appear here after each weekly review.",
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: entries.length,
            itemBuilder: (context, index) => _EntryCard(entry: entries[index]),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text("Error: $e")),
      ),
    );
  }
}

class _EntryCard extends StatelessWidget {
  final AdaptationEntry entry;
  const _EntryCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final date = DateTime.tryParse(entry.createdAt);
    final dateStr = date != null
        ? "${date.day}/${date.month}/${date.year}"
        : entry.createdAt;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  entry.agentType.contains("adapter") ? Icons.auto_fix_high : Icons.psychology,
                  size: 20,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Text(
                  _formatAgentType(entry.agentType),
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.primary,
                  ),
                ),
                const Spacer(),
                Text(dateStr, style: theme.textTheme.bodySmall),
              ],
            ),
            if (entry.summary != null) ...[
              const SizedBox(height: 8),
              Text(entry.summary!, style: theme.textTheme.bodyMedium),
            ],
            if (entry.rules.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 4,
                children: entry.rules
                    .map((r) => Chip(
                          label: Text(r, style: const TextStyle(fontSize: 11)),
                          padding: EdgeInsets.zero,
                          visualDensity: VisualDensity.compact,
                        ))
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _formatAgentType(String type) {
    switch (type) {
      case "adapter":
        return "AI Adaptation";
      case "adapter_rules_only":
        return "Auto-Adjustment";
      case "planner":
        return "Plan Generation";
      default:
        return type;
    }
  }
}
