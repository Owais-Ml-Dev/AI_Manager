import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../domain/profile_data.dart';

final profileProvider = AsyncNotifierProvider<ProfileController, ProfileData>(
  ProfileController.new,
);

class ProfileController extends AsyncNotifier<ProfileData> {
  static const _nameKey = 'profile_name';

  static const _emailKey = 'profile_email';

  @override
  Future<ProfileData> build() async {
    final preferences = await SharedPreferences.getInstance();

    return ProfileData(
      name: preferences.getString(_nameKey) ?? 'User',
      email: preferences.getString(_emailKey) ?? '',
    );
  }

  Future<void> save({required String name, required String email}) async {
    final cleanName = name.trim().isEmpty ? 'User' : name.trim();

    final cleanEmail = email.trim();

    final preferences = await SharedPreferences.getInstance();

    await preferences.setString(_nameKey, cleanName);

    await preferences.setString(_emailKey, cleanEmail);

    state = AsyncData(ProfileData(name: cleanName, email: cleanEmail));
  }
}
