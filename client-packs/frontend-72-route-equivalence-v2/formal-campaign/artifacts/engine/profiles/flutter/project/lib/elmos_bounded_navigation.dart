// Direct identity projection for bounded-navigation-v1 compatibility; no second route literal is permitted.
import 'elmos_bounded_interaction.dart';

typedef ElmosBoundedRoute = Map<String, Object?>;
extension ElmosBoundedRouteFields on ElmosBoundedRoute {
  String get id => this['id']! as String;
  String get path => this['path']! as String;
  String get title => this['title']! as String;
  String get text => this['text']! as String;
  bool get requiresAuth => this['requiresAuth']! as bool;
  bool get deepLink => this['deepLink']! as bool;
}
final Map<String, Object?> elmosBoundedNavigation = <String, Object?>{
  'routes': elmosFrontendInteractionNavigation['routes']!,
};
final List<Object?> elmosBoundedRoutes = elmosBoundedNavigation['routes']! as List<Object?>;
ElmosBoundedRoute elmosRoute(Object? raw) => raw! as ElmosBoundedRoute;
ElmosBoundedRoute get elmosFirstRoute => elmosRoute(elmosBoundedRoutes.first);
ElmosBoundedRoute elmosSelectBoundedRoute(String path) {
  if (elmosBoundedRoutes.isEmpty) throw StateError('bounded navigation requires at least one route');
  return elmosRoute(elmosBoundedRoutes.firstWhere((raw) => elmosRoute(raw).path == path, orElse: () => elmosBoundedRoutes.first));
}
