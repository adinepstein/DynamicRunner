import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";

import "package:dynamicrunner/src/features/auth/sign_in_screen.dart";

void main() {
  testWidgets("SignInScreen shows email and password fields", (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SignInScreen(),
      ),
    );

    expect(find.byType(TextField), findsNWidgets(2));
    expect(find.widgetWithText(FilledButton, "Sign in"), findsOneWidget);
    expect(find.widgetWithText(TextButton, "Create account"), findsOneWidget);
  });
}
