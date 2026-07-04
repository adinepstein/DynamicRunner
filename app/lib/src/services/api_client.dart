import "dart:convert";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:http/http.dart" as http;
import "package:supabase_flutter/supabase_flutter.dart";

/// Base URL for the DynamicRunner backend API.
const _kApiBaseUrl = String.fromEnvironment(
  "API_BASE_URL",
  defaultValue: "http://10.0.2.2:8000",
);

/// Provides an authenticated HTTP client that attaches the Supabase JWT.
final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

class ApiClient {
  final String baseUrl = _kApiBaseUrl;

  Future<Map<String, String>> _headers() async {
    final session = Supabase.instance.client.auth.currentSession;
    return {
      "Content-Type": "application/json",
      if (session != null) "Authorization": "Bearer ${session.accessToken}",
    };
  }

  Future<ApiResponse> post(String path, {Map<String, dynamic>? body}) async {
    final url = Uri.parse("$baseUrl$path");
    final headers = await _headers();
    debugPrint("[ApiClient] POST $url");

    final response = await http.post(
      url,
      headers: headers,
      body: body != null ? jsonEncode(body) : null,
    );

    return ApiResponse(
      statusCode: response.statusCode,
      body: _parseBody(response.body),
    );
  }

  Future<ApiResponse> get(String path) async {
    final url = Uri.parse("$baseUrl$path");
    final headers = await _headers();
    debugPrint("[ApiClient] GET $url");

    final response = await http.get(url, headers: headers);

    return ApiResponse(
      statusCode: response.statusCode,
      body: _parseBody(response.body),
    );
  }

  Future<ApiResponse> delete(String path, {Map<String, String>? queryParams}) async {
    var url = Uri.parse("$baseUrl$path");
    if (queryParams != null && queryParams.isNotEmpty) {
      url = url.replace(queryParameters: queryParams);
    }
    final headers = await _headers();
    debugPrint("[ApiClient] DELETE $url");

    final response = await http.delete(url, headers: headers);

    return ApiResponse(
      statusCode: response.statusCode,
      body: _parseBody(response.body),
    );
  }

  Map<String, dynamic> _parseBody(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } catch (_) {
      return {"raw": body};
    }
  }
}

class ApiResponse {
  final int statusCode;
  final Map<String, dynamic> body;

  const ApiResponse({required this.statusCode, required this.body});

  bool get isOk => statusCode >= 200 && statusCode < 300;

  String get errorMessage {
    return body["detail"]?.toString() ?? body["error"]?.toString() ?? "Unknown error ($statusCode)";
  }
}
