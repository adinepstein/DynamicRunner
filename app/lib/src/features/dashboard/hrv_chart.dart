import "dart:convert";

import "package:fl_chart/fl_chart.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../services/api_client.dart";

class HrvData {
  final List<HrvDay> days;
  final double? baseline;
  final double? sd;

  HrvData({required this.days, this.baseline, this.sd});
}

class HrvDay {
  final String date;
  final double? hrv;
  final double? rhr;
  final double? sleepHours;

  HrvDay({required this.date, this.hrv, this.rhr, this.sleepHours});
}

final hrvChartProvider = FutureProvider.autoDispose<HrvData?>((ref) async {
  final api = ref.read(apiClientProvider);
  final resp = await api.get("/dashboard/training-load?days=28");
  if (!resp.isOk) return null;

  final body = resp.body;
  final List<dynamic> items;
  double? baseline;
  double? sd;

  if (body["hrv"] is List) {
    items = body["hrv"] as List<dynamic>;
    baseline = (body["hrv_baseline"] as num?)?.toDouble();
    sd = (body["hrv_sd"] as num?)?.toDouble();
  } else if (body["raw"] is String) {
    final decoded = jsonDecode(body["raw"] as String);
    items = (decoded["hrv"] as List<dynamic>?) ?? [];
    baseline = (decoded["hrv_baseline"] as num?)?.toDouble();
    sd = (decoded["hrv_sd"] as num?)?.toDouble();
  } else {
    return null;
  }

  final days = items.map((e) {
    final m = e as Map<String, dynamic>;
    return HrvDay(
      date: m["date"] as String? ?? "",
      hrv: (m["hrv"] as num?)?.toDouble(),
      rhr: (m["rhr"] as num?)?.toDouble(),
      sleepHours: (m["sleep_hours"] as num?)?.toDouble(),
    );
  }).toList();

  return HrvData(days: days, baseline: baseline, sd: sd);
});

class HrvTrendChart extends ConsumerWidget {
  const HrvTrendChart({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(hrvChartProvider);

    return dataAsync.when(
      data: (data) {
        if (data == null || data.days.isEmpty) {
          return const SizedBox(
            height: 200,
            child: Center(child: Text("No HRV data yet")),
          );
        }
        return _HrvChart(data: data);
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

class _HrvChart extends StatelessWidget {
  final HrvData data;
  const _HrvChart({required this.data});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final days = data.days.where((d) => d.hrv != null).toList();

    if (days.isEmpty) {
      return const SizedBox(height: 200, child: Center(child: Text("No HRV readings")));
    }

    final spots = <FlSpot>[];
    for (int i = 0; i < days.length; i++) {
      spots.add(FlSpot(i.toDouble(), days[i].hrv!));
    }

    final latestHrv = days.last.hrv!;
    final baselineStr = data.baseline != null ? data.baseline!.toStringAsFixed(0) : "—";

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Text("HRV Trend", style: theme.textTheme.titleMedium),
              const Spacer(),
              Text(
                "Today: ${latestHrv.toStringAsFixed(0)} ms  |  Baseline: $baselineStr ms",
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
        SizedBox(
          height: 180,
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
                extraLinesData: ExtraLinesData(
                  horizontalLines: [
                    if (data.baseline != null)
                      HorizontalLine(
                        y: data.baseline!,
                        color: Colors.purple.withAlpha(128),
                        strokeWidth: 1.5,
                        dashArray: [6, 4],
                        label: HorizontalLineLabel(
                          show: true,
                          labelResolver: (_) => "Baseline",
                          style: const TextStyle(fontSize: 10, color: Colors.purple),
                        ),
                      ),
                    if (data.baseline != null && data.sd != null) ...[
                      HorizontalLine(
                        y: data.baseline! + data.sd!,
                        color: Colors.green.withAlpha(64),
                        strokeWidth: 1,
                        dashArray: [3, 5],
                      ),
                      HorizontalLine(
                        y: data.baseline! - data.sd!,
                        color: Colors.red.withAlpha(64),
                        strokeWidth: 1,
                        dashArray: [3, 5],
                      ),
                    ],
                  ],
                ),
                lineBarsData: [
                  LineChartBarData(
                    spots: spots,
                    isCurved: true,
                    color: theme.colorScheme.primary,
                    barWidth: 2,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, _, __, ___) => FlDotCirclePainter(
                        radius: 3,
                        color: theme.colorScheme.primary,
                        strokeWidth: 0,
                      ),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      color: theme.colorScheme.primary.withAlpha(30),
                    ),
                  ),
                ],
                lineTouchData: LineTouchData(
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipItems: (spots) {
                      return spots.map((s) {
                        return LineTooltipItem(
                          "${s.y.toStringAsFixed(0)} ms",
                          TextStyle(color: theme.colorScheme.primary),
                        );
                      }).toList();
                    },
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
