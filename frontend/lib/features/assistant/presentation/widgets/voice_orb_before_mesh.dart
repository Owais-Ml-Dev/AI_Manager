import 'dart:math' as math;

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
    this.size = 255,
  });

  @override
  State<VoiceOrb> createState() {
    return _VoiceOrbState();
  }
}

class _VoiceOrbState extends State<VoiceOrb>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,

      builder: (context, child) {
        return CustomPaint(
          size: Size.square(widget.size),

          painter: _VoiceOrbPainter(
            progress: _controller.value,

            level: widget.level,

            listening: widget.listening,

            speaking: widget.speaking,

            muted: widget.muted,

            failed: widget.failed,
          ),
        );
      },
    );
  }
}

class _VoiceOrbPainter extends CustomPainter {
  final double progress;
  final double level;

  final bool listening;
  final bool speaking;
  final bool muted;
  final bool failed;

  const _VoiceOrbPainter({
    required this.progress,
    required this.level,
    required this.listening,
    required this.speaking,
    required this.muted,
    required this.failed,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);

    final active = listening || speaking;

    final normalizedLevel = level.clamp(0.0, 1.0);

    final baseRadius = size.width * 0.305;

    final pulse = active ? (math.sin(progress * math.pi * 2) * 2.2) : 0.0;

    final radius = baseRadius + pulse;

    // ========================================================
    // COLORS
    // ========================================================

    final cyan = failed ? const Color(0xFFFF4C4C) : const Color(0xFFF2F2F2);

    final blue = failed ? const Color(0xFF7A1616) : const Color(0xFF8E8E93);

    final purple = failed ? const Color(0xFF9E2929) : const Color(0xFFBDBDC2);

    // ========================================================
    // EXTERNAL WAVEFORM
    // ========================================================

    if (!muted) {
      _drawWave(
        canvas,
        size,
        center.dy,
        normalizedLevel,
        progress,
        cyan,
        purple,
        outside: true,
      );
    }

    // ========================================================
    // OUTER GLOW
    // ========================================================

    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8 + normalizedLevel * 7
      ..color = cyan.withValues(
        alpha: failed ? 0.22 : 0.18 + normalizedLevel * 0.18,
      )
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 22);

    canvas.drawCircle(center, radius + 4, glowPaint);

    // ========================================================
    // SPHERE
    // ========================================================

    final sphereRect = Rect.fromCircle(center: center, radius: radius);

    final spherePaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.35, -0.4),

        radius: 1.25,

        colors: failed
            ? const [Color(0xFF321010), Color(0xFF170808), Color(0xFF080506)]
            : const [Color(0xFF292929), Color(0xFF171717), Color(0xFF080808)],

        stops: const [0.0, 0.55, 1.0],
      ).createShader(sphereRect);

    canvas.drawCircle(center, radius, spherePaint);

    // ========================================================
    // SPHERE BORDER
    // ========================================================

    final borderPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.7
      ..shader = SweepGradient(
        startAngle: 0,
        endAngle: math.pi * 2,

        colors: [cyan, blue, purple, cyan],

        transform: GradientRotation(progress * math.pi * 2),
      ).createShader(sphereRect);

    canvas.drawCircle(center, radius, borderPaint);

    // ========================================================
    // INTERNAL WAVE
    // ========================================================

    canvas.save();

    final clip = Path()..addOval(sphereRect);

    canvas.clipPath(clip);

    if (!muted) {
      _drawWave(
        canvas,
        size,
        center.dy,
        normalizedLevel,
        progress,
        cyan,
        purple,
        outside: false,
      );

      _drawParticles(
        canvas,
        size,
        center,
        radius,
        normalizedLevel,
        progress,
        cyan,
        purple,
      );
    }

    canvas.restore();

    // ========================================================
    // MUTED ICON
    // ========================================================

    if (muted) {
      final iconPainter = TextPainter(
        text: const TextSpan(
          text: '?',
          style: TextStyle(color: Colors.white70, fontSize: 18),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

      iconPainter.paint(
        canvas,
        center - Offset(iconPainter.width / 2, iconPainter.height / 2),
      );
    }
  }

  void _drawWave(
    Canvas canvas,
    Size size,
    double centerY,
    double level,
    double progress,
    Color first,
    Color second, {
    required bool outside,
  }) {
    final path = Path();

    final amplitude = (outside ? 8 : 12) + level * (outside ? 24 : 30);

    final phase = progress * math.pi * 2;

    const step = 3.0;

    for (double x = 0; x <= size.width; x += step) {
      final normalized = x / size.width;

      final envelope = math.sin(normalized * math.pi);

      final waveOne = math.sin(normalized * math.pi * 7 + phase);

      final waveTwo = math.sin(normalized * math.pi * 13 - phase * 0.72) * 0.34;

      final y = centerY + (waveOne + waveTwo) * amplitude * envelope;

      if (x == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }

    final rect = Rect.fromLTWH(0, centerY - 55, size.width, 110);

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = outside ? 1.25 : 2.0
      ..shader = LinearGradient(
        colors: [
          first.withValues(alpha: outside ? 0.12 : 0.70),
          second.withValues(alpha: outside ? 0.50 : 0.82),
          first.withValues(alpha: outside ? 0.12 : 0.70),
        ],
      ).createShader(rect);

    if (!outside) {
      paint.maskFilter = const MaskFilter.blur(BlurStyle.normal, 1.5);
    }

    canvas.drawPath(path, paint);
  }

  void _drawParticles(
    Canvas canvas,
    Size size,
    Offset center,
    double radius,
    double level,
    double progress,
    Color first,
    Color second,
  ) {
    final phase = progress * math.pi * 2;

    final count = 28 + (level * 24).round();

    for (var i = 0; i < count; i++) {
      final t = i / (count - 1);

      final x = center.dx - radius * 0.92 + (radius * 1.84 * t);

      final envelope = math.sin(t * math.pi);

      final y =
          center.dy +
          math.sin(t * math.pi * 9 + phase + i * 0.17) *
              (5 + level * 19) *
              envelope;

      final offset = math.sin(i * 12.3 + phase * 1.8) * (3 + level * 5);

      final particleColor = i.isEven ? first : second;

      final paint = Paint()
        ..color = particleColor.withValues(alpha: 0.25 + level * 0.55);

      canvas.drawCircle(Offset(x, y + offset), 0.8 + level * 1.15, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _VoiceOrbPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.level != level ||
        oldDelegate.listening != listening ||
        oldDelegate.speaking != speaking ||
        oldDelegate.muted != muted ||
        oldDelegate.failed != failed;
  }
}
