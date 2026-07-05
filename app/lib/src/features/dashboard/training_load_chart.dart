import "dart:convert";

import "package:fl_chart/fl_chart.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class TrainingLoadData {
  final List<DailyLoad> days;
  TrainingLoadData({required this.days});
}

class DailyLoad {
  final String date;
  final double ctl;
  final double atl;
  final double tsb;
  final double acwr;

  DailyLoad({
    required this.date,
    required this.ctl,
    required this.atl,
    required this.tsb,
    required this.acwr,
  });
}

final trainingLoadProvider = FutureProvider.autoDispose<TrainingLoadData?>((ref) async {
  final api = ref.read(apiClientProvider);
  final resp = await api.get("/dashboard/training-load?days=42");
  if (!resp.isOk) return null;

  final body = resp.body;
  final List<dynamic> items;
  if (body["training_load"] is List) {
    items = body["training_load"] as List<dynamic>;
  } else if (body["raw"] is String) {
    final decoded = jsonDecode(body["raw"] as String);
    items = (decoded["training_load"] as List<dynamic>?) ?? [];
  } else {
    return null;
  }

  final days = items.map((e) {
    final m = e as Map<String, dynamic>;
    return DailyLoad(
      date: m["date"] as String? ?? "",
      ctl: (m["ctl"] as num?)?.toDouble() ?? 0,
      atl: (m["atl"] as num?)?.toDouble() ?? 0,
      tsb: (m["tsb"] as num?)?.toDouble() ?? 0,
      acwr: (m["acwr"] as num?)?.toDouble() ?? 0,
    );
  }).toList();

  return TrainingLoadData(days: days);
});

class TrainingLoadChart extends ConsumerWidget {
  const TrainingLoadChart({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(trainingLoadProvider);

    return dataAsync.when(
      data: (data) {
        if (data == null || data.days.isEmpty) {
          return const SizedBox(
            height: 200,
            child: Center(child: Text("No training data yet")),
          );
        }
        return _Chart(data: data);
      },
      loading: () => const SizedBox(
        height: 200,
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => SizedBox(
        height: 200,
        child: Center(child: Text("Error: $e")),
      ),
    );
  }
}

class _Chart extends StatelessWidget {
  final TrainingLoadData data;
  const _Chart({required this.data});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final days = data.days;

    final ctlSpots = <FlSpot>[];
    final atlSpots = <FlSpot>[];
    final tsbSpots = <FlSpot>[];

    for (int i = 0; i < days.length; i++) {
      ctlSpots.add(FlSpot(i.toDouble(), days[i].ctl));
      atlSpots.add(FlSpot(i.toDouble(), days[i].atl));
      tsbSpots.add(FlSpot(i.toDouble(), days[i].tsb));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Text("Training Load", style: theme.textTheme.titleMedium),
        ),
        SizedBox(
          height: 200,
          child: Padding(
            padding: const EdgeInsets.only(right: 16, left: 8),
            child: LineChart(
              LineChartData(
                gridData: const FlGridData(show: true, drawVerticalLine: false),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      interval: 7,
                      getTitlesWidget: (value, _) {
                        final idx = value.toInt();
                        if (idx >= 0 && idx < days.length) {
                          final d = days[idx].date;
                          return Text(d.substring(5), style: const TextStyle(fontSize: 10));
                        }
                        return const Text("");
                      },
                    ),
                  ),
                  leftTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: true, reservedSize: 36),
                  ),
                ),
                lineBarsData: [
                  LineChartBarData(
                    spots: ctlSpots,
                    isCurved: true,
                    color: Colors.blue,
                    barWidth: 2,
                    dotData: const FlDotData(show: false),
                  ),
                  LineChartBarData(
                    spots: atlSpots,
                    isCurved: true,
                    color: Colors.orange,
                    barWidth: 2,
                    dotData: const FlDotData(show: false),
                  ),
                  LineChartBarData(
                    spots: tsbSpots,
                    isCurved: true,
                    color: Colors.green,
                    barWidth: 1.5,
                    dashArray: [4, 4],
                    dotData: const FlDotData(show: false),
                  ),
                ],
                lineTouchData: LineTouchData(
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipItems: (spots) {
                      return spots.map((s) {
                        final labels = ["CTL", "ATL", "TSB"];
                        final colors = [Colors.blue, Colors.orange, Colors.green];
                        return LineTooltipItem(
                          "${labels[s.barIndex]}: ${s.y.toStringAsFixed(1)}",
                          TextStyle(color: colors[s.barIndex], fontSize: 12),
                        );
                      }).toList();
                    },
                  ),
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _LegendDot(color: Colors.blue, label: "Fitness (CTL)"),
              const SizedBox(width: 12),
              _LegendDot(color: Colors.orange, label: "Fatigue (ATL)"),
              const SizedBox(width: 12),
              _LegendDot(color: Colors.green, label: "Form (TSB)"),
            ],
          ),
        ),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 11)),
      ],
    );
  }
}
