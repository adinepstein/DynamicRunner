import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";
import "../plan/plan_provider.dart";

/// Screen for reordering this week's workouts via drag-and-drop.
class EditWeekScreen extends ConsumerStatefulWidget {
  const EditWeekScreen({super.key});

  @override
  ConsumerState<EditWeekScreen> createState() => _EditWeekScreenState();
}

class _EditWeekScreenState extends ConsumerState<EditWeekScreen> {
  List<PlannedWorkout>? _workouts;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  bool _hasChanges = false;

  @override
  void initState() {
    super.initState();
    _loadWeek();
  }

  Future<void> _loadWeek() async {
    final api = ref.read(apiClientProvider);
    final now = DateTime.now();

    // Get start of week (Monday)
    final monday = now.subtract(Duration(days: now.weekday - 1));
    final sunday = monday.add(const Duration(days: 6));

    final from = "${monday.year}-${monday.month.toString().padLeft(2, '0')}-${monday.day.toString().padLeft(2, '0')}";
    final to = "${sunday.year}-${sunday.month.toString().padLeft(2, '0')}-${sunday.day.toString().padLeft(2, '0')}";

    final resp = await api.get("/plan/workouts?from_date=$from&to_date=$to");
    if (!resp.isOk) {
      setState(() {
        _error = "Failed to load workouts";
        _loading = false;
      });
      return;
    }

    final raw = resp.body["raw"];
    if (raw != null && raw is String) {
      try {
        final items = jsonDecode(raw) as List<dynamic>;
        setState(() {
          _workouts = items
              .map((e) => PlannedWorkout.fromJson(e as Map<String, dynamic>))
              .toList();
          _loading = false;
        });
        return;
      } catch (_) {}
    }

    setState(() {
      _workouts = [];
      _loading = false;
    });
  }

  void _onReorder(int oldIndex, int newIndex) {
    if (oldIndex < newIndex) {
      newIndex -= 1;
    }
    setState(() {
      final item = _workouts!.removeAt(oldIndex);
      _workouts!.insert(newIndex, item);
      _hasChanges = true;
    });
  }

  Future<void> _save() async {
    if (_workouts == null || !_hasChanges) return;

    setState(() => _saving = true);

    final api = ref.read(apiClientProvider);

    // Build reorder payload — map new order to new dates
    final originalDates = _workouts!.map((w) => w.scheduledDate).toList();
    originalDates.sort();

    final moves = <Map<String, String>>[];
    for (int i = 0; i < _workouts!.length; i++) {
      if (i < originalDates.length && _workouts![i].scheduledDate != originalDates[i]) {
        moves.add({
          "workout_id": _workouts![i].id,
          "new_date": originalDates[i],
        });
      }
    }

    if (moves.isNotEmpty) {
      final resp = await api.post("/plan/reorder", body: {"moves": moves});
      if (resp.isOk) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text("Week updated")),
          );
        }
        setState(() => _hasChanges = false);
        _loadWeek();
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text("Failed to save changes")),
          );
        }
      }
    }

    setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Edit This Week"),
        actions: [
          if (_hasChanges)
            TextButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text("Save"),
            ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Text(_error!));
    if (_workouts == null || _workouts!.isEmpty) {
      return const Center(child: Text("No workouts this week"));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            "Long-press and drag to reorder workouts within this week.",
            style: TextStyle(color: Colors.grey),
          ),
        ),
        Expanded(
          child: ReorderableListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: _workouts!.length,
            onReorder: _onReorder,
            itemBuilder: (context, index) {
              final w = _workouts![index];
              return _WorkoutTile(key: ValueKey(w.id), workout: w);
            },
          ),
        ),
      ],
    );
  }
}

class _WorkoutTile extends StatelessWidget {
  final PlannedWorkout workout;
  const _WorkoutTile({super.key, required this.workout});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isRest = workout.type == "rest";

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: Icon(
          isRest ? Icons.bed : _iconForType(workout.type),
          color: isRest ? Colors.grey : theme.colorScheme.primary,
        ),
        title: Text(workout.title),
        subtitle: Text(
          "${workout.scheduledDate}  •  ${workout.type}",
        ),
        trailing: const Icon(Icons.drag_handle),
      ),
    );
  }

  IconData _iconForType(String type) {
    switch (type) {
      case "intervals":
      case "threshold":
      case "tempo":
        return Icons.speed;
      case "long":
        return Icons.terrain;
      case "easy":
      case "recovery":
        return Icons.directions_walk;
      default:
        return Icons.directions_run;
    }
  }
}
