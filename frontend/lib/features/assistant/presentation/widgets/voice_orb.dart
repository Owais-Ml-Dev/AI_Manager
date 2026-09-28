import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

class VoiceOrb extends StatefulWidget {
  final double level;

  final bool listening;
  final bool speaking;
  final bool muted;
  final bool failed;

  final double size;

  const VoiceOrb({
    super.key,
    required this.level,
    required this.listening,
    required this.speaking,
    required this.muted,
    required this.failed,
    this.size = 280,
  });

  @override
  State<VoiceOrb> createState() {
    return _VoiceOrbState();
  }
}

class _VoiceOrbState extends State<VoiceOrb>
    with SingleTickerProviderStateMixin {
  ui.FragmentProgram? _program;

  late final AnimationController _animation;

  Object? _loadError;

  @override
  void initState() {
    super.initState();

    _animation = AnimationController(
      vsync: this,

      duration: const Duration(seconds: 12),
    )..repeat();

    unawaited(_loadShader());
  }

  Future<void> _loadShader() async {
    try {
      final program = await ui.FragmentProgram.fromAsset(
        'assets/shaders/voice_mesh.frag',
      );

      if (!mounted) {
        return;
      }

      setState(() {
        _program = program;

        _loadError = null;
      });
    } catch (error, stackTrace) {
      debugPrint(
        '[VOICE ORB] Shader load error: '
        '$error',
      );

      debugPrint('$stackTrace');

      if (!mounted) {
        return;
      }

      setState(() {
        _loadError = error;
      });
    }
  }

  @override
  void dispose() {
    _animation.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loadError != null) {
      return _FallbackMeshOrb(
        level: widget.level,
        size: widget.size,
        failed: widget.failed,
      );
    }

    final program = _program;

    if (program == null) {
      return SizedBox.square(
        dimension: widget.size,

        child: const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }

    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _animation,

        builder: (context, child) {
          return CustomPaint(
            size: Size.square(widget.size),

            painter: _MeshOrbPainter(
              program: program,

              time: _animation.value * 12.0,

              level: widget.level,

              speaking: widget.speaking,

              muted: widget.muted,

              failed: widget.failed,
            ),
          );
        },
      ),
    );
  }
}

class _MeshOrbPainter extends CustomPainter {
  final ui.FragmentProgram program;

  final double time;
  final double level;

  final bool speaking;
  final bool muted;
  final bool failed;

  const _MeshOrbPainter({
    required this.program,
    required this.time,
    required this.level,
    required this.speaking,
    required this.muted,
    required this.failed,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final shader = program.fragmentShader();

    // --------------------------------------------------------
    // Shader uniform order:
    //
    // 0 -> uSize.x
    // 1 -> uSize.y
    // 2 -> uTime
    // 3 -> uLevel
    // 4 -> uSpeaking
    // 5 -> uMuted
    // 6 -> uFailed
    // --------------------------------------------------------

    shader.setFloat(0, size.width);

    shader.setFloat(1, size.height);

    shader.setFloat(2, time);

    shader.setFloat(3, level.clamp(0.0, 1.0));

    shader.setFloat(4, speaking ? 1.0 : 0.0);

    shader.setFloat(5, muted ? 1.0 : 0.0);

    shader.setFloat(6, failed ? 1.0 : 0.0);

    final paint = Paint()..shader = shader;

    canvas.drawRect(Offset.zero & size, paint);
  }

  @override
  bool shouldRepaint(covariant _MeshOrbPainter oldDelegate) {
    return oldDelegate.time != time ||
        oldDelegate.level != level ||
        oldDelegate.speaking != speaking ||
        oldDelegate.muted != muted ||
        oldDelegate.failed != failed;
  }
}

// ============================================================
// FALLBACK
// ============================================================
//
// If a particular device cannot compile the shader,
// Voice Mode still remains usable.
//

class _FallbackMeshOrb extends StatelessWidget {
  final double level;
  final double size;
  final bool failed;

  const _FallbackMeshOrb({
    required this.level,
    required this.size,
    required this.failed,
  });

  @override
  Widget build(BuildContext context) {
    final normalized = level.clamp(0.0, 1.0);

    return SizedBox.square(
      dimension: size,

      child: Center(
        child: Container(
          width: size * (0.58 + normalized * 0.035),

          height: size * (0.58 + normalized * 0.035),

          decoration: BoxDecoration(
            shape: BoxShape.circle,

            gradient: RadialGradient(
              colors: failed
                  ? const [Color(0xFF341515), Color(0xFF080808)]
                  : const [Color(0xFF292929), Color(0xFF090909)],
            ),

            border: Border.all(
              color: failed ? Colors.redAccent : Colors.white70,

              width: 1.3,
            ),

            boxShadow: [
              BoxShadow(
                color: failed
                    ? Colors.redAccent.withValues(alpha: 0.18)
                    : Colors.white.withValues(alpha: 0.08 + normalized * 0.10),

                blurRadius: 28,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
