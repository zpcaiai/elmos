import 'package:flutter_test/flutter_test.dart';
import 'package:interaction_flutter/elmos_bounded_navigation.dart';
void main() {
  test('preserves all generated routes', () { expect(elmosBoundedRoutes.length, 3); expect(elmosBoundedRoutes.map((raw) => elmosRoute(raw).path).toSet().length, elmosBoundedRoutes.length); });
}
