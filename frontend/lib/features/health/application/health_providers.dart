import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client_provider.dart';
import '../data/health_repository.dart';

final healthRepositoryProvider = Provider<HealthRepository>((ref) {
  return HealthRepository(ref.watch(apiClientProvider));
});

final backendHealthProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.watch(healthRepositoryProvider).checkBackend();
});

final databaseHealthProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(healthRepositoryProvider).checkDatabase();
});
