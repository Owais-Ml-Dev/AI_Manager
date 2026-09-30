from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('frontend').resolve()
screen = root / 'lib/features/assistant/presentation/assistant_screen.dart'
model = root / 'lib/features/assistant/domain/assistant_message.dart'


def read(p):
    return p.read_text(encoding='utf-8-sig')

def write(p, s):
    p.write_text(s, encoding='utf-8')

def rep(p, old, new, count=1):
    s = read(p)
    if old not in s:
        raise RuntimeError(f'Expected block not found in {p}: {old[:100]!r}')
    write(p, s.replace(old, new, count))

# Backups
for p in (screen, model):
    backup = p.with_suffix(p.suffix + '.before_message_actions.bak')
    if not backup.exists():
        backup.write_text(read(p), encoding='utf-8')

# ------------------------------------------------------------------
# 1) Message model: edit/retry metadata
# ------------------------------------------------------------------
write(model, '''class AssistantMessage {
  final String text;
  final bool fromUser;
  final String? provider;
  final String? model;
  final bool fallbackUsed;

  /// True only for user messages that can safely become a new top-level
  /// request when edited. Follow-up answers inside a server-owned task draft
  /// deliberately keep this false.
  final bool allowEdit;

  /// Original user text that may safely be retried for a normal AI reply.
  /// Task-flow messages do not populate this because retrying them blindly
  /// can advance a server-side draft twice.
  final String? retryText;

  const AssistantMessage({
    required this.text,
    required this.fromUser,
    this.provider,
    this.model,
    this.fallbackUsed = false,
    this.allowEdit = false,
    this.retryText,
  });
}
''')

# ------------------------------------------------------------------
# 2) Flutter services import for clipboard
# ------------------------------------------------------------------
rep(
    screen,
    "import 'package:flutter/material.dart';\n",
    "import 'package:flutter/material.dart';\nimport 'package:flutter/services.dart';\n",
)

# ------------------------------------------------------------------
# 3) Focus node
# ------------------------------------------------------------------
rep(
    screen,
    "  final _messageController = TextEditingController();\n  final _scrollController = ScrollController();\n",
    "  final _messageController = TextEditingController();\n  final _messageFocusNode = FocusNode();\n  final _scrollController = ScrollController();\n",
)
rep(
    screen,
    "    _messageController.dispose();\n    _scrollController.dispose();\n",
    "    _messageController.dispose();\n    _messageFocusNode.dispose();\n    _scrollController.dispose();\n",
)

# ------------------------------------------------------------------
# 4) Mark only top-level user messages editable
# ------------------------------------------------------------------
old = '''    setState(() {
      _suggestions = const [];
      _messages.add(AssistantMessage(text: message, fromUser: true));
      _messageController.clear();
      _activeCancelToken = CancelToken();
      _sending = true;
    });'''
new = '''    final allowEdit = _activeBatchId == null && _activeDraftId == null;

    setState(() {
      _suggestions = const [];
      _messages.add(
        AssistantMessage(
          text: message,
          fromUser: true,
          allowEdit: allowEdit,
        ),
      );
      _messageController.clear();
      _activeCancelToken = CancelToken();
      _sending = true;
    });'''
rep(screen, old, new)

# ------------------------------------------------------------------
# 5) Normal assistant chat reply remembers safe retry text
# ------------------------------------------------------------------
old = '''          AssistantMessage(
            text: result.reply,
            fromUser: false,
            provider: result.provider,
            model: result.model,
            fallbackUsed: result.fallbackUsed,
          ),'''
new = '''          AssistantMessage(
            text: result.reply,
            fromUser: false,
            provider: result.provider,
            model: result.model,
            fallbackUsed: result.fallbackUsed,
            retryText: message,
          ),'''
rep(screen, old, new)

# ------------------------------------------------------------------
# 6) Clipboard/Edit/Retry helpers before _finishSending
# ------------------------------------------------------------------
anchor = '''  void _finishSending() {
'''
helpers = r'''  Future<void> _copyMessageText(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Copied to clipboard.'),
        duration: Duration(milliseconds: 1200),
      ),
    );
  }

  Future<void> _editSentMessage(int index) async {
    if (_sending || index < 0 || index >= _messages.length) return;

    final message = _messages[index];
    if (!message.fromUser || !message.allowEdit) return;

    // Editing an original request creates a new branch locally. If the user
    // has already progressed beyond Task 1, previous confirmed task changes
    // may already exist in MongoDB and cannot be rolled back automatically.
    final progressedBatch =
        _activeBatchId != null && (_activeBatchTaskNumber ?? 1) > 1;

    if (progressedBatch) {
      final proceed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Edit this request?'),
          content: const Text(
            'Some earlier tasks in this batch may already have been saved. '
            'Editing will start a new request and will not undo saved tasks.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Edit anyway'),
            ),
          ],
        ),
      );

      if (proceed != true || !mounted) return;
    }

    if (_activeBatchId != null) {
      await _forgetActiveBatch();
      if (!mounted) return;
    }

    setState(() {
      // Remove the old branch from the visible conversation. Server-side
      // drafts/batches are TTL-backed and are no longer referenced locally.
      if (index + 1 < _messages.length) {
        _messages.removeRange(index + 1, _messages.length);
      }
      _messages.removeAt(index);

      _activeBatchId = null;
      _activeBatchTaskNumber = null;
      _activeBatchTotalTasks = null;
      _activeDraftId = null;
      _pendingCommand = null;
      _selectedMatchId = null;
      _suggestions = const [];

      _messageController.value = TextEditingValue(
        text: message.text,
        selection: TextSelection.collapsed(offset: message.text.length),
      );
    });

    _messageFocusNode.requestFocus();
  }

  Future<void> _retryAssistantMessage(String text) async {
    if (_sending) return;

    if (_activeBatchId != null || _activeDraftId != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Finish or cancel the current task flow before trying an older '
            'AI reply again.',
          ),
        ),
      );
      return;
    }

    _messageController.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    _messageFocusNode.requestFocus();
    await _send();
  }

'''
rep(screen, anchor, helpers + anchor)

# ------------------------------------------------------------------
# 7) Pass actions to each bubble
# ------------------------------------------------------------------
old = '''                    itemBuilder: (context, index) {
                      return _MessageBubble(message: _messages[index]);
                    },'''
new = '''                    itemBuilder: (context, index) {
                      final message = _messages[index];
                      return _MessageBubble(
                        message: message,
                        onCopy: () => _copyMessageText(message.text),
                        onEdit: message.fromUser && message.allowEdit
                            ? () => _editSentMessage(index)
                            : null,
                        onRetry:
                            !message.fromUser && message.retryText != null
                            ? () => _retryAssistantMessage(message.retryText!)
                            : null,
                      );
                    },'''
rep(screen, old, new)

# ------------------------------------------------------------------
# 8) Wire FocusNode into composer
# ------------------------------------------------------------------
rep(
    screen,
    '''              child: TextField(
                controller: _messageController,
''',
    '''              child: TextField(
                controller: _messageController,
                focusNode: _messageFocusNode,
''',
)

# ------------------------------------------------------------------
# 9) Replace message bubble with bubble + action icons
# ------------------------------------------------------------------
start = read(screen).find('class _MessageBubble extends StatelessWidget {')
if start == -1:
    raise RuntimeError('Could not find _MessageBubble class.')

replacement = r'''class _MessageBubble extends StatelessWidget {
  final AssistantMessage message;
  final VoidCallback onCopy;
  final VoidCallback? onEdit;
  final VoidCallback? onRetry;

  const _MessageBubble({
    required this.message,
    required this.onCopy,
    this.onEdit,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final user = message.fromUser;
    final colors = AppColors.of(context);

    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Column(
        crossAxisAlignment:
            user ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Container(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.sizeOf(context).width * 0.82,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: user ? colors.white : colors.surface,
              borderRadius: BorderRadius.circular(16),
              border: user ? null : Border.all(color: colors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  message.text,
                  style: TextStyle(
                    color: user ? colors.onAccent : colors.textPrimary,
                    fontSize: 13,
                    height: 1.45,
                  ),
                ),
                if (!user &&
                    message.model != null &&
                    message.model!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    _providerLabel(),
                    style: TextStyle(
                      color: colors.textMuted,
                      fontSize: 9,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 3),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (onEdit != null)
                _MessageActionButton(
                  tooltip: 'Edit',
                  icon: Icons.edit_outlined,
                  onPressed: onEdit!,
                ),
              _MessageActionButton(
                tooltip: 'Copy',
                icon: Icons.copy_all_outlined,
                onPressed: onCopy,
              ),
              if (onRetry != null)
                _MessageActionButton(
                  tooltip: 'Try again',
                  icon: Icons.refresh_rounded,
                  onPressed: onRetry!,
                ),
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }

  String _providerLabel() {
    final raw = message.provider?.trim().toLowerCase();

    final provider = switch (raw) {
      'gemini' => 'Gemini',
      'groq' => 'Groq',
      'cloudflare' => 'Cloudflare',
      'openrouter' => 'OpenRouter',
      'cerebras' => 'Cerebras',
      'mistral' => 'Mistral',
      'nvidia' => 'NVIDIA',
      _ =>
        message.provider?.trim().isNotEmpty == true
            ? message.provider!.trim()
            : 'AI',
    };

    final model = message.model?.trim() ?? '';

    final parts = <String>[
      provider,
      if (model.isNotEmpty) model,
      if (message.fallbackUsed) 'fallback',
    ];

    return parts.join(' · ');
  }
}

class _MessageActionButton extends StatelessWidget {
  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  const _MessageActionButton({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      visualDensity: VisualDensity.compact,
      padding: const EdgeInsets.all(5),
      constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
      icon: Icon(
        icon,
        size: 17,
        color: AppColors.of(context).textMuted,
      ),
    );
  }
}
'''

s = read(screen)
# _MessageBubble is the final class in this file, so replace to EOF.
s = s[:start] + replacement
write(screen, s)

print('Message actions patch applied successfully.')
print('Added: Edit + Copy on top-level user messages; Copy + Try again on safe AI replies.')
