import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class FeedbackButton extends ConsumerWidget {
  const FeedbackButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return FloatingActionButton.small(
      heroTag: "feedback",
      onPressed: () => _showFeedbackDialog(context, ref),
      child: const Icon(Icons.feedback_outlined),
    );
  }

  void _showFeedbackDialog(BuildContext context, WidgetRef ref) {
    final controller = TextEditingController();
    String category = "general";

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text("Send Feedback"),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: "bug", label: Text("Bug")),
                  ButtonSegment(value: "feature", label: Text("Feature")),
                  ButtonSegment(value: "general", label: Text("General")),
                ],
                selected: {category},
                onSelectionChanged: (s) => setState(() => category = s.first),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                maxLines: 4,
                decoration: const InputDecoration(
                  hintText: "What's on your mind?",
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("Cancel"),
            ),
            FilledButton(
              onPressed: () async {
                if (controller.text.trim().isEmpty) return;
                final api = ref.read(apiClientProvider);
                await api.post("/feedback", body: {
                  "category": category,
                  "message": controller.text.trim(),
                });
                if (ctx.mounted) {
                  Navigator.pop(ctx);
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text("Thanks for your feedback!")),
                  );
                }
              },
              child: const Text("Send"),
            ),
          ],
        ),
      ),
    );
  }
}
