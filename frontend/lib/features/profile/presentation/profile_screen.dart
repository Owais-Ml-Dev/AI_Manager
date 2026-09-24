import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../settings/presentation/settings_screen.dart';
import '../application/profile_provider.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() {
    return _ProfileScreenState();
  }
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _nameController = TextEditingController();

  final _emailController = TextEditingController();

  bool _loadedInitialValues = false;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();

    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) {
      return;
    }

    setState(() {
      _saving = true;
    });

    try {
      await ref
          .read(profileProvider.notifier)
          .save(name: _nameController.text, email: _emailController.text);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Profile saved.')));
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(profileProvider);

    return Scaffold(
      body: SafeArea(
        child: profile.when(
          loading: () => const Center(child: CircularProgressIndicator()),

          error: (error, stackTrace) => Center(
            child: Text(
              'Could not load profile.',
              style: TextStyle(color: AppColors.of(context).textSecondary),
            ),
          ),

          data: (data) {
            if (!_loadedInitialValues) {
              _nameController.text = data.name;

              _emailController.text = data.email;

              _loadedInitialValues = true;
            }

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
              children: [
                Row(
                  children: [
                    IconButton(
                      onPressed: () {
                        Navigator.pop(context);
                      },
                      icon: const Icon(Icons.arrow_back),
                    ),

                    const SizedBox(width: 4),

                    Text(
                      'Profile',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ],
                ),

                const SizedBox(height: 32),

                Center(
                  child: Container(
                    width: 84,
                    height: 84,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.of(context).surfaceElevated,
                      border: Border.all(color: AppColors.of(context).border),
                    ),
                    child: Text(
                      data.initials,
                      style: TextStyle(
                        color: AppColors.of(context).textPrimary,
                        fontSize: 28,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),

                const SizedBox(height: 14),

                Center(
                  child: Text(
                    data.name,
                    style: TextStyle(
                      color: AppColors.of(context).textPrimary,
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),

                const SizedBox(height: 5),

                Center(
                  child: Text(
                    data.email.isEmpty ? 'Local profile' : data.email,
                    style: TextStyle(
                      color: AppColors.of(context).textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ),

                const SizedBox(height: 36),

                Text(
                  'Personal information',
                  style: TextStyle(
                    color: AppColors.of(context).textPrimary,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                const SizedBox(height: 14),

                TextField(
                  controller: _nameController,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(
                    labelText: 'Name',
                    hintText: 'Your name',
                  ),
                ),

                const SizedBox(height: 12),

                TextField(
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                    labelText: 'Email',
                    hintText: 'Optional',
                  ),
                ),

                const SizedBox(height: 16),

                FilledButton(
                  onPressed: _saving ? null : _save,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(double.infinity, 52),
                    backgroundColor: AppColors.of(context).white,
                    foregroundColor: AppColors.of(context).onAccent,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save profile'),
                ),

                const SizedBox(height: 32),

                Text(
                  'App',
                  style: TextStyle(
                    color: AppColors.of(context).textPrimary,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                const SizedBox(height: 12),

                _ProfileRow(
                  icon: Icons.settings_outlined,
                  title: 'Settings',
                  subtitle: 'Appearance and AI settings',
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) {
                          return const SettingsScreen();
                        },
                      ),
                    );
                  },
                ),

                const SizedBox(height: 10),

                _ProfileRow(
                  icon: Icons.info_outline,
                  title: 'AI Task Manager',
                  subtitle: 'Version 1.0.0',
                  onTap: null,
                ),

                const SizedBox(height: 22),

                Text(
                  'Your profile is stored locally on this device. '
                  'Account sign-in can be added later.',
                  style: TextStyle(
                    color: AppColors.of(context).textMuted,
                    fontSize: 11,
                    height: 1.5,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _ProfileRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  const _ProfileRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: colors.border),
          ),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: colors.surfaceElevated,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, size: 20, color: colors.textSecondary),
              ),

              const SizedBox(width: 13),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: colors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),

                    const SizedBox(height: 3),

                    Text(
                      subtitle,
                      style: TextStyle(
                        color: colors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),

              if (onTap != null)
                Icon(Icons.chevron_right, color: colors.textMuted, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
