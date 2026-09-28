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

  final _keyControllers = <String, TextEditingController>{
    'gemini': TextEditingController(),
    'groq': TextEditingController(),
    'cloudflare': TextEditingController(),
    'openrouter': TextEditingController(),
  };

  final _cloudflareAccountController = TextEditingController();

  final _obscure = <String, bool>{
    'gemini': true,
    'groq': true,
    'cloudflare': true,
    'openrouter': true,
  };

  String _selectedProvider = 'gemini';

  String? _savingProvider;

  @override
  void initState() {
    super.initState();

    _future = _load();
  }

  @override
  void dispose() {
    for (final controller in _keyControllers.values) {
      controller.dispose();
    }

    _cloudflareAccountController.dispose();

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

  Future<void> _saveProvider(String provider) async {
    if (_savingProvider != null) {
      return;
    }

    final key = _keyControllers[provider]!.text.trim();

    if (key.isEmpty) {
      _showMessage('Enter the ${_label(provider)} API key first.');

      return;
    }

    final accountId = provider == 'cloudflare'
        ? _cloudflareAccountController.text.trim()
        : null;

    setState(() {
      _savingProvider = provider;
    });

    try {
      await ref
          .read(assistantSettingsRepositoryProvider)
          .testAndSaveProvider(provider, key, accountId: accountId);

      _keyControllers[provider]!.clear();

      if (provider == 'cloudflare') {
        _cloudflareAccountController.clear();
      }

      if (!mounted) {
        return;
      }

      _showMessage(
        '${_label(provider)} credentials tested and saved securely.',
      );

      await _reload();
    } on ApiException catch (error) {
      if (mounted) {
        _showMessage(error.message);
      }
    } catch (_) {
      if (mounted) {
        _showMessage('Could not save ${_label(provider)} credentials.');
      }
    } finally {
      if (mounted) {
        setState(() {
          _savingProvider = null;
        });
      }
    }
  }

  Future<void> _confirmDeleteProvider(String provider) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text('Delete ${_label(provider)} credentials?'),
          content: Text(
            '${_label(provider)} will no longer be available '
            'in the automatic fallback chain.',
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
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() {
      _savingProvider = provider;
    });

    try {
      await ref
          .read(assistantSettingsRepositoryProvider)
          .deleteProvider(provider);

      if (!mounted) {
        return;
      }

      _showMessage('${_label(provider)} credentials removed.');

      await _reload();
    } finally {
      if (mounted) {
        setState(() {
          _savingProvider = null;
        });
      }
    }
  }

  String _label(String provider) {
    switch (provider) {
      case 'gemini':
        return 'Gemini';

      case 'groq':
        return 'Groq';

      case 'cloudflare':
        return 'Cloudflare Workers AI';

      case 'openrouter':
        return 'OpenRouter Free';

      default:
        return provider;
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

    final selected = data.provider(_selectedProvider);

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 50),
      children: [
        // ==================================================
        // APPEARANCE
        // ==================================================

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
              Icon(Icons.dark_mode_outlined, color: colors.textSecondary),

              const SizedBox(width: 12),

              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Dark mode',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Use the dark app appearance',
                      style: TextStyle(fontSize: 11),
                    ),
                  ],
                ),
              ),

              Switch(
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

        // ==================================================
        // AI PROVIDERS
        // ==================================================
        const Text(
          'AI Providers',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),

        const SizedBox(height: 5),

        Text(
          'Select a provider and enter its API credentials.',
          style: TextStyle(
            color: colors.textSecondary,
            fontSize: 12,
            height: 1.4,
          ),
        ),

        const SizedBox(height: 14),

        // ==================================================
        // FALLBACK STATUS
        // ==================================================
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: colors.surfaceElevated,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.swap_vert_circle_outlined, size: 19),
                  SizedBox(width: 8),
                  Text(
                    'Automatic fallback',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  Spacer(),
                  Text('ON', style: TextStyle(fontWeight: FontWeight.w700)),
                ],
              ),

              const SizedBox(height: 9),

              Text(
                'Gemini ? Groq ? Cloudflare ? OpenRouter Free',
                style: TextStyle(
                  color: colors.textSecondary,
                  fontSize: 11,
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 14),

        // ==================================================
        // PROVIDER DROPDOWN
        // ==================================================
        DropdownButtonFormField<String>(
          initialValue: _selectedProvider,
          decoration: InputDecoration(
            labelText: 'Provider',
            prefixIcon: const Icon(Icons.smart_toy_outlined),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
          ),
          items: data.providers.map((item) {
            return DropdownMenuItem<String>(
              value: item.provider,
              child: Row(
                children: [
                  Expanded(child: Text(item.label)),

                  if (item.configured)
                    const Icon(
                      Icons.check_circle,
                      size: 16,
                      color: AppColors.green,
                    ),
                ],
              ),
            );
          }).toList(),
          onChanged: _savingProvider != null
              ? null
              : (value) {
                  if (value == null) {
                    return;
                  }

                  setState(() {
                    _selectedProvider = value;
                  });
                },
        ),

        const SizedBox(height: 14),

        if (selected != null) _selectedProviderCard(selected),

        const SizedBox(height: 18),

        // ==================================================
        // COMPACT CONFIGURED PROVIDERS
        // ==================================================
        Text(
          'Configured providers',
          style: TextStyle(
            color: colors.textSecondary,
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),

        const SizedBox(height: 8),

        Wrap(
          spacing: 7,
          runSpacing: 7,
          children: data.providers.map((item) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: item.configured
                    ? colors.surfaceElevated
                    : colors.surface,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: colors.border),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    item.configured
                        ? Icons.check_circle_outline
                        : Icons.circle_outlined,
                    size: 14,
                    color: item.configured ? AppColors.green : colors.textMuted,
                  ),

                  const SizedBox(width: 5),

                  Text(
                    item.label,
                    style: TextStyle(
                      fontSize: 10,
                      color: item.configured
                          ? colors.textPrimary
                          : colors.textMuted,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),

        const SizedBox(height: 18),

        _InfoCard(
          icon: Icons.psychology_outlined,
          title: 'Reasoning',
          subtitle:
              'Task execution remains deterministic after AI interpretation',
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

  Widget _selectedProviderCard(AssistantProviderSettings item) {
    final colors = AppColors.of(context);

    final busy = _savingProvider == item.provider;

    final controller = _keyControllers[item.provider]!;

    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // PROVIDER HEADER

          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.label,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),

                    const SizedBox(height: 3),

                    Text(
                      item.model,
                      style: TextStyle(
                        color: colors.textSecondary,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),

              if (item.configured)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.check_circle_outline,
                      size: 17,
                      color: AppColors.green,
                    ),

                    const SizedBox(width: 5),

                    Text(
                      item.keyHint ?? '****',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),

                    IconButton(
                      tooltip: 'Delete credentials',
                      onPressed: _savingProvider != null
                          ? null
                          : () => _confirmDeleteProvider(item.provider),
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
                )
              else
                Text(
                  'Not configured',
                  style: TextStyle(color: colors.textMuted, fontSize: 11),
                ),
            ],
          ),

          if (item.provider == 'gemini') ...[
            const SizedBox(height: 6),
            Text(
              'Gemini is also used by Live Voice.',
              style: TextStyle(color: colors.textSecondary, fontSize: 10),
            ),
          ],

          const SizedBox(height: 14),

          // CLOUDFLARE ACCOUNT ID ONLY
          if (item.requiresAccountId) ...[
            TextField(
              controller: _cloudflareAccountController,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                hintText: item.accountId == null
                    ? 'Cloudflare Account ID'
                    : 'Account ID saved: ${_accountHint(item.accountId!)}',
                prefixIcon: const Icon(Icons.badge_outlined),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
            ),

            const SizedBox(height: 10),
          ],

          // API KEY
          TextField(
            controller: controller,
            obscureText: _obscure[item.provider] ?? true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              hintText: item.configured
                  ? 'Enter a new key to replace it'
                  : 'Enter API key / token',
              prefixIcon: const Icon(Icons.key_outlined),
              suffixIcon: IconButton(
                onPressed: () {
                  setState(() {
                    _obscure[item.provider] =
                        !(_obscure[item.provider] ?? true);
                  });
                },
                icon: Icon(
                  (_obscure[item.provider] ?? true)
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

          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _savingProvider != null
                  ? null
                  : () => _saveProvider(item.provider),
              child: Text(
                busy
                    ? 'Checking...'
                    : item.configured
                    ? 'Test & replace'
                    : 'Test & save',
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _accountHint(String accountId) {
    if (accountId.length <= 8) {
      return accountId;
    }

    return '${accountId.substring(0, 4)}?'
        '${accountId.substring(accountId.length - 4)}';
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
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: colors.textSecondary),

          const SizedBox(width: 12),

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

                const SizedBox(height: 2),

                Text(
                  subtitle,
                  style: TextStyle(color: colors.textSecondary, fontSize: 10),
                ),
              ],
            ),
          ),

          Text(
            value,
            style: TextStyle(
              color: valueColor,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
