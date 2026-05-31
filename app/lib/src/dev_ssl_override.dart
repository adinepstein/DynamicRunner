import "dart:io";

/// DEV ONLY — bypasses TLS certificate validation.
///
/// Use when the Android emulator cannot verify HTTPS (e.g. corporate proxy/VPN).
/// Enable with `--dart-define=ALLOW_INSECURE_SSL=true` in **debug** builds only.
/// Never enable for release/production.
class DevSslHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback = (_, __, ___) => true;
  }
}
