import 'package:flutter/foundation.dart';

abstract final class ApiConfig {
  static String get baseUrl {
    if (kIsWeb) {
      return 'http://127.0.0.1:5000';
    }

    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        // Android emulator -> Windows host machine.
        return 'http://10.0.2.2:5000';

      case TargetPlatform.iOS:
      case TargetPlatform.macOS:
      case TargetPlatform.windows:
      case TargetPlatform.linux:
      case TargetPlatform.fuchsia:
        return 'http://127.0.0.1:5000';
    }
  }

  static const connectTimeout = Duration(seconds: 10);

  // Must stay >= the backend's GEMINI_TIMEOUT_SECONDS (+ a buffer for the
  // backend's own retry). At 30s this was firing BEFORE the backend's own
  // 60s Gemini timeout, so the app showed "took too long" even on requests
  // Gemini would have answered a few seconds later. Backend now retries
  // once on a transient error too, so give it enough room for that retry.
  static const receiveTimeout = Duration(seconds: 70);
}
