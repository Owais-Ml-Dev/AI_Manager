class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final String? errorCode;
  final bool retryable;

  const ApiException({
    required this.message,
    this.statusCode,
    this.errorCode,
    this.retryable = false,
  });

  @override
  String toString() {
    return message;
  }
}
