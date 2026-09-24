import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client_provider.dart';
import '../data/history_repository.dart';
import '../domain/history_item.dart';

final historyRepositoryProvider = Provider<HistoryRepository>((ref) {
  return HistoryRepository(ref.watch(apiClientProvider));
});

final historyDataProvider = FutureProvider<HistoryData>((ref) async {
  return ref.watch(historyRepositoryProvider).fetchHistory();
});
