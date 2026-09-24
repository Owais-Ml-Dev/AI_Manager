import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client_provider.dart';
import '../data/home_repository.dart';
import '../domain/home_task_item.dart';

final homeRepositoryProvider = Provider<HomeRepository>((ref) {
  return HomeRepository(ref.watch(apiClientProvider));
});

final homeDataProvider = FutureProvider<HomeData>((ref) async {
  return ref.watch(homeRepositoryProvider).fetchHome();
});
