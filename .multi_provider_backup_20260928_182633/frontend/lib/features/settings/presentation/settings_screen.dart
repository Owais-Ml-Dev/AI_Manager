import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/theme_mode_provider.dart';
import '../application/assistant_settings_providers.dart';
import '../domain/assistant_settings_data.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() {
    return _SettingsScreenState();
  }
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late Future<AssistantSettingsData> _future;

  final _apiKeyController = TextEditingController();

  bool _obscureApiKey = true;

  bool _savingKey = false;

  @override
  void initState() {
    super.initState();

    _future = _load();
  }

  @override
  void dispose() {
    _apiKeyController.dispose();

    super.dispose();
  }

  Future<AssistantSettingsData> _load() {
    return ref.read(assistantSettingsRepositoryProvider).fetch();
  }

  Future<void> _reload() async {
    setState(() {
      _future = _load();
    });

    await _future;
  }

  Future<void> _saveApiKey() async {
    if (_savingKey) {
      return;
    }

    final value = _apiKeyController.text.trim();

    if (value.isEmpty) {
      _showMessage('Enter your Gemini API key first.');

      return;
    }

    setState(() {
      _savingKey = true;
    });

    try {
      await ref.read(assistantSettingsRepositoryProvider).saveApiKey(value);

      _apiKeyController.clear();

      if (!mounted) {
        return;
      }

      _showMessage('Gemini API key tested and saved securely on this device.');

      await _reload();
    } on ApiException catch (error) {
      if (mounted) {
        _showMessage(error.message);
      }
    } catch (_) {
      if (mounted) {
        _showMessage('Could not save the Gemini API key.');
      }
    } finally {
      if (mounted) {
        setState(() {
          _savingKey = false;
        });
      }
    }
  }

  Future<void> _confirmDeleteApiKey() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Delete Gemini API key?'),
          content: const Text(
            'The saved Gemini API key will be removed '
            'from this device. The AI Assistant will stop '
            'working until you add another key.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context, false);
              },
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context, true);
              },
              style: TextButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
              child: const Text('Delete key'),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {
      await _deleteApiKey();
    }
  }

  Future<void> _deleteApiKey() async {
    if (_savingKey) {
      return;
    }

    setState(() {
      _savingKey = true;
    });

    try {
      await ref.read(assistantSettingsRepositoryProvider).deleteApiKey();

      _apiKeyController.clear();

      if (!mounted) {
        return;
      }

      _showMessage('Gemini API key removed from this device.');

      await _reload();
    } finally {
      if (mounted) {
        setState(() {
          _savingKey = false;
        });
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.of(context).background,
        elevation: 0,
        title: const Text('Settings'),
      ),
      body: FutureBuilder<AssistantSettingsData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting &&
              !snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError || !snapshot.hasData) {
            return _errorView();
          }

          return RefreshIndicator(
            onRefresh: _reload,
            child: _content(snapshot.data!, themeMode),
          );
        },
      ),
    );
  }

  Widget _content(AssistantSettingsData data, ThemeMode themeMode) {
    final colors = AppColors.of(context);

    final ready = data.configured && data.available;

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 50),
      children: [
        const Text(
          'Appearance',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),

        const SizedBox(height: 5),

        Text(
          'Choose how AI Task Manager looks.',
          style: TextStyle(color: colors.textSecondary, fontSize: 12),
        ),

        const SizedBox(height: 18),

        Container(
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 11),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(15),
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
                child: Icon(
                  themeMode == ThemeMode.dark
                      ? Icons.dark_mode_outlined
                      : Icons.light_mode_outlined,
                  size: 20,
                ),
              ),

              const SizedBox(width: 13),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Dark mode',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),

                    const SizedBox(height: 3),

                    Text(
                      themeMode == ThemeMode.dark
                          ? 'Dark appearance'
                          : 'Light appearance',
                      style: TextStyle(
                        color: colors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),

              Switch.adaptive(
                value: themeMode == ThemeMode.dark,
                onChanged: (enabled) {
                  ref
                      .read(themeModeProvider.notifier)
                      .setMode(enabled ? ThemeMode.dark : ThemeMode.light);
                },
              ),
            ],
          ),
        ),

        const SizedBox(height: 30),

        const Text(
          'AI Assistant',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),

        const SizedBox(height: 5),

        Text(
          'Use your own Google Gemini API key. '
          'The key is stored securely on this device.',
          style: TextStyle(
            color: colors.textSecondary,
            fontSize: 12,
            height: 1.4,
          ),
        ),

        const SizedBox(height: 18),

        Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(15),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Gemini API key',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),

              const SizedBox(height: 5),

              if (data.storedKeyConfigured)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: colors.surfaceElevated,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: colors.border),
                  ),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.check_circle_outline,
                        size: 18,
                        color: AppColors.green,
                      ),

                      const SizedBox(width: 8),

                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Stored securely',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),

                            const SizedBox(height: 2),

                            Text(
                              'Saved on this device',
                              style: TextStyle(
                                color: colors.textSecondary,
                                fontSize: 10,
                              ),
                            ),
                          ],
                        ),
                      ),

                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            data.keyHint ?? '****',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),

                          const SizedBox(width: 4),

                          IconButton(
                            tooltip: 'Delete API key',
                            onPressed: _savingKey ? null : _confirmDeleteApiKey,
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(
                              minWidth: 32,
                              minHeight: 32,
                            ),
                            icon: Icon(
                              Icons.delete_outline,
                              size: 17,
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                )
              else
                Text(
                  'No Gemini API key is saved on this device.',
                  style: TextStyle(color: colors.textSecondary, fontSize: 11),
                ),

              const SizedBox(height: 14),

              TextField(
                controller: _apiKeyController,
                obscureText: _obscureApiKey,
                autocorrect: false,
                enableSuggestions: false,
                decoration: InputDecoration(
                  hintText: data.storedKeyConfigured
                      ? 'Enter a new key to replace it'
                      : 'Enter Gemini API key',
                  prefixIcon: const Icon(Icons.key_outlined),
                  suffixIcon: IconButton(
                    onPressed: () {
                      setState(() {
                        _obscureApiKey = !_obscureApiKey;
                      });
                    },
                    icon: Icon(
                      _obscureApiKey
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),

              const SizedBox(height: 12),

              Row(
                children: [
                  Expanded(
                    child: FilledButton(
                      onPressed: _savingKey ? null : _saveApiKey,
                      child: Text(_savingKey ? 'Checking...' : 'Test & save'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 10),

        _InfoCard(
          icon: Icons.auto_awesome,
          title: 'Gemini',
          subtitle: data.model.isEmpty ? 'Google AI' : data.model,
          value: ready
              ? 'Ready'
              : data.configured
              ? 'Unavailable'
              : 'API key needed',
          valueColor: ready ? AppColors.green : colors.textMuted,
        ),

        const SizedBox(height: 10),

        _InfoCard(
          icon: Icons.psychology_outlined,
          title: 'Reasoning',
          subtitle: 'Adjusted automatically for each request',
          value: 'Automatic',
          valueColor: colors.textPrimary,
        ),

        if (data.message.isNotEmpty) ...[
          const SizedBox(height: 18),

          Text(
            data.message,
            style: TextStyle(
              color: colors.textSecondary,
              fontSize: 11,
              height: 1.4,
            ),
          ),
        ],
      ],
    );
  }

  Widget _errorView() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.error_outline,
            size: 38,
            color: AppColors.of(context).textMuted,
          ),

          const SizedBox(height: 12),

          const Text('Could not load settings.'),

          const SizedBox(height: 12),

          TextButton(onPressed: _reload, child: const Text('Try again')),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final IconData icon;

  final String title;

  final String subtitle;

  final String value;

  final Color valueColor;

  const _InfoCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(15),
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
            child: Icon(icon, size: 20),
          ),

          const SizedBox(width: 13),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                const SizedBox(height: 3),

                Text(
                  subtitle,
                  style: TextStyle(color: colors.textSecondary, fontSize: 11),
                ),
              ],
            ),
          ),

          const SizedBox(width: 10),

          Text(
            value,
            style: TextStyle(
              color: valueColor,
              fontSize: 10,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
