import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "hrv_chart.dart";
import "plan_progress_widget.dart";
import "training_load_chart.dart";

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text("Dashboard")),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(trainingLoadProvider);
          ref.invalidate(hrvChartProvider);
          ref.invalidate(planProgressProvider);
        },
        child: const SingleChildScrollView(
          physics: AlwaysScrollableScrollPhysics(),
          child: Column(
            children: [
              PlanProgressWidget(),
              SizedBox(height: 8),
              TrainingLoadChart(),
              SizedBox(height: 16),
              HrvTrendChart(),
              SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}
