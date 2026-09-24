import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client_provider.dart';
import '../data/dashboard_repository.dart';
import '../domain/dashboard_data.dart';

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  return DashboardRepository(ref.watch(apiClientProvider));
});

final dashboardDataProvider = FutureProvider<DashboardData>((ref) async {
  return ref.watch(dashboardRepositoryProvider).fetchDashboard();
});
