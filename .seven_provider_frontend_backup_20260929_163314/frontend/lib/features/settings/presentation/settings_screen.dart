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
  bool _savingFallback = false;

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

  Future<void> _setAutoFallback(bool enabled) async {
    if (_savingFallback) {
      return;
    }

    setState(() {
      _savingFallback = true;
    });

    try {
      await ref
          .read(assistantSettingsRepositoryProvider)
          .saveAutoFallback(enabled);

      if (!mounted) {
        return;
      }

      await _reload();

      if (!mounted) {
        return;
      }

      _showMessage(
        enabled
            ? 'Automatic fallback enabled.'
            : 'Automatic fallback disabled.',
      );
    } on ApiException catch (error) {
      if (mounted) {
        _showMessage(error.message);
      }
    } catch (_) {
      if (mounted) {
        _showMessage('Could not update automatic fallback.');
      }
    } finally {
      if (mounted) {
        setState(() {
          _savingFallback = false;
        });
      }
    }
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

    final configuredCount = data.providers
        .where((item) => item.configured)
        .length;

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
      children: [
        // ==================================================
        // APPEARANCE
        // ==================================================

        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: colors.border),
          ),
          child: Row(
            children: [
              Icon(
                Icons.dark_mode_outlined,
                size: 21,
                color: colors.textSecondary,
              ),

              const SizedBox(width: 12),

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

                    const SizedBox(height: 2),

                    Text(
                      'Use the dark app appearance',
                      style: TextStyle(
                        color: colors.textSecondary,
                        fontSize: 10,
                      ),
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

        const SizedBox(height: 28),

        // ==================================================
        // AI PROVIDER
        // ==================================================
        const Text(
          'AI Provider',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),

        const SizedBox(height: 4),

        Text(
          'Select a provider and configure its API credentials.',
          style: TextStyle(color: colors.textSecondary, fontSize: 11),
        ),

        const SizedBox(height: 14),

        Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ============================================
              // PROVIDER DROPDOWN
              // ============================================

              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _selectedProvider,
                decoration: InputDecoration(
                  labelText: 'Provider',
                  prefixIcon: const Icon(Icons.smart_toy_outlined, size: 20),
                  filled: true,
                  fillColor: colors.surfaceElevated,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(13),
                    borderSide: BorderSide(color: colors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(13),
                    borderSide: BorderSide(color: colors.border),
                  ),
                ),
                items: data.providers.map((item) {
                  return DropdownMenuItem<String>(
                    value: item.provider,
                    child: Text(item.label),
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

              if (selected != null) ...[
                const SizedBox(height: 16),

                _selectedProviderCard(selected),
              ],

              const SizedBox(height: 16),

              Divider(height: 1, color: colors.border),

              const SizedBox(height: 14),

              // ============================================
              // FALLBACK - COMPACT
              // ============================================
              Row(
                children: [
                  Icon(
                    Icons.swap_horiz_rounded,
                    size: 18,
                    color: colors.textSecondary,
                  ),

                  const SizedBox(width: 8),

                  const Expanded(
                    child: Text(
                      'Automatic fallback',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),

                  Text(
                    data.autoFallback ? 'ON' : 'OFF',
                    style: TextStyle(
                      color: data.autoFallback
                          ? AppColors.green
                          : colors.textMuted,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),

                  const SizedBox(width: 4),

                  Transform.scale(
                    scale: 0.78,
                    child: Switch.adaptive(
                      value: data.autoFallback,
                      onChanged: _savingFallback ? null : _setAutoFallback,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 7),

              Text(
                data.autoFallback
                    ? 'Gemini > Groq > Cloudflare > OpenRouter'
                    : 'Fallback disabled',

                style: TextStyle(color: colors.textSecondary, fontSize: 9.5),
              ),

              const SizedBox(height: 5),

              Text(
                '$configuredCount of ${data.providers.length} providers configured',
                style: TextStyle(color: colors.textMuted, fontSize: 9),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _selectedProviderCard(AssistantProviderSettings item) {
    final colors = AppColors.of(context);

    final busy = _savingProvider == item.provider;

    final controller = _keyControllers[item.provider]!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ================================================
        // STATUS
        // ================================================

        Row(
          children: [
            Icon(
              item.configured ? Icons.check_circle : Icons.circle_outlined,
              size: 16,
              color: item.configured ? AppColors.green : colors.textMuted,
            ),

            const SizedBox(width: 7),

            Text(
              item.configured ? 'Configured' : 'Not configured',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: item.configured ? colors.textPrimary : colors.textMuted,
              ),
            ),

            const Spacer(),

            if (item.configured) ...[
              Text(
                item.keyHint ?? '****',
                style: TextStyle(
                  color: colors.textSecondary,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),

              const SizedBox(width: 3),

              IconButton(
                tooltip: 'Delete credentials',
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
                onPressed: _savingProvider != null
                    ? null
                    : () => _confirmDeleteProvider(item.provider),
                icon: Icon(
                  Icons.delete_outline,
                  size: 16,
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ],
          ],
        ),

        const SizedBox(height: 3),

        Padding(
          padding: const EdgeInsets.only(left: 23),
          child: Text(
            item.model,
            style: TextStyle(color: colors.textMuted, fontSize: 9),
          ),
        ),

        if (item.provider == 'gemini') ...[
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsets.only(left: 23),
            child: Text(
              'Also used for Live Voice',
              style: TextStyle(color: colors.textMuted, fontSize: 9),
            ),
          ),
        ],

        const SizedBox(height: 14),

        // ================================================
        // CLOUDFLARE ACCOUNT ID
        // ================================================
        if (item.requiresAccountId) ...[
          TextField(
            controller: _cloudflareAccountController,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              hintText: item.accountId == null
                  ? 'Cloudflare Account ID'
                  : 'Account ID: ${_accountHint(item.accountId!)}',
              prefixIcon: const Icon(Icons.badge_outlined, size: 20),
              filled: true,
              fillColor: colors.surfaceElevated,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(13),
              ),
            ),
          ),

          const SizedBox(height: 10),
        ],

        // ================================================
        // API KEY
        // ================================================
        TextField(
          controller: controller,
          obscureText: _obscure[item.provider] ?? true,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(
            hintText: item.configured
                ? 'Enter a new key to replace it'
                : 'Enter API key / token',
            prefixIcon: const Icon(Icons.key_outlined, size: 20),
            suffixIcon: IconButton(
              onPressed: () {
                setState(() {
                  _obscure[item.provider] = !(_obscure[item.provider] ?? true);
                });
              },
              icon: Icon(
                (_obscure[item.provider] ?? true)
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
                size: 20,
              ),
            ),
            filled: true,
            fillColor: colors.surfaceElevated,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(13)),
          ),
        ),

        const SizedBox(height: 11),

        SizedBox(
          width: double.infinity,
          height: 44,
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
