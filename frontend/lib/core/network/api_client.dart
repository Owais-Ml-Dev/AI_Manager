import 'package:dio/dio.dart';

import 'api_config.dart';
import 'api_exception.dart';

class ApiClient {
  late final Dio _dio;

  ApiClient({Dio? dio}) {
    _dio =
        dio ??
        Dio(
          BaseOptions(
            baseUrl: ApiConfig.baseUrl,
            connectTimeout: ApiConfig.connectTimeout,
            receiveTimeout: ApiConfig.receiveTimeout,
            headers: const {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
            },
          ),
        );
  }

  Future<dynamic> get(
    String path, {
    Map<String, dynamic>? queryParameters,
    Map<String, dynamic>? headers,
  }) async {
    try {
      final response = await _dio.get(
        path,
        queryParameters: queryParameters,
        options: headers == null ? null : Options(headers: headers),
      );

      return _extractResponse(response);
    } on DioException catch (error) {
      throw _mapError(error);
    }
  }

  Future<dynamic> post(
    String path, {
    Object? data,
    CancelToken? cancelToken,
    Map<String, dynamic>? headers,
  }) async {
    try {
      final response = await _dio.post(
        path,
        data: data,
        cancelToken: cancelToken,
        options: headers == null ? null : Options(headers: headers),
      );

      return _extractResponse(response);
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) {
        rethrow;
      }

      throw _mapError(error);
    }
  }

  Future<dynamic> put(String path, {Object? data}) async {
    try {
      final response = await _dio.put(path, data: data);

      return _extractResponse(response);
    } on DioException catch (error) {
      throw _mapError(error);
    }
  }

  Future<dynamic> patch(String path, {Object? data}) async {
    try {
      final response = await _dio.patch(path, data: data);

      return _extractResponse(response);
    } on DioException catch (error) {
      throw _mapError(error);
    }
  }

  Future<dynamic> delete(String path, {Object? data}) async {
    try {
      final response = await _dio.delete(path, data: data);

      return _extractResponse(response);
    } on DioException catch (error) {
      throw _mapError(error);
    }
  }

  dynamic _extractResponse(Response<dynamic> response) {
    final body = response.data;

    if (body is Map<String, dynamic>) {
      final success = body['success'];

      if (success == false) {
        throw ApiException(
          message: body['message']?.toString() ?? 'Request failed.',
          statusCode: response.statusCode,
          errorCode: body['error_code']?.toString(),
          retryable: body['retryable'] == true,
        );
      }

      if (body.containsKey('data')) {
        return body['data'];
      }
    }

    return body;
  }

  ApiException _mapError(DioException error) {
    final response = error.response;

    final body = response?.data;

    if (body is Map) {
      return ApiException(
        message: body['message']?.toString() ?? 'The server returned an error.',
        statusCode: response?.statusCode,
        errorCode: body['error_code']?.toString(),
        retryable: body['retryable'] == true,
      );
    }

    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiException(
          message: 'The backend took too long to respond.',
          retryable: true,
        );

      case DioExceptionType.connectionError:
        return const ApiException(
          message: 'Could not connect to the backend.',
          retryable: true,
        );

      default:
        return ApiException(
          message: error.message ?? 'Unexpected network error.',
          retryable: true,
        );
    }
  }
}
