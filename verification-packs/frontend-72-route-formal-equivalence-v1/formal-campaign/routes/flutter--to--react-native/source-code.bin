// Generated executable proof boundary for bounded-navigation-v1.
import 'dart:convert';

const String elmosBoundedNavigationBase64 = "eyJzY2hlbWFWZXJzaW9uIjoiMS4wIiwicHJvZmlsZSI6ImJvdW5kZWQtbmF2aWdhdGlvbi12MSIsInByb2plY3RUaXRsZSI6IkVMTU9TIOacieeVjOWvvOiIqumqjOivgSIsIm5hdmlnYXRpb24iOnsibGFiZWwiOiLkuLvopoHlr7zoiKoifSwicmVuZGVyIjp7Im1haW5Sb2xlIjoibWFpbiIsImhlYWRpbmdMZXZlbCI6MX0sImZhbGxiYWNrIjp7InN0cmF0ZWd5IjoiRklSU1RfREVDTEFSRURfUk9VVEUifSwicm91dGVzIjpbeyJpZCI6InJvdXRlLmhvbWUiLCJwYXRoIjoiLyIsInRpdGxlIjoiY29tcG9uZW50LmhvbWUiLCJ0ZXh0Ijoi6aaW6aG15YaF5a65IiwicmVxdWlyZXNBdXRoIjpmYWxzZSwiZGVlcExpbmsiOnRydWV9LHsiaWQiOiJyb3V0ZS5hY2NvdW50IiwicGF0aCI6Ii9hY2NvdW50IiwidGl0bGUiOiJjb21wb25lbnQuYWNjb3VudCIsInRleHQiOiLotKbmiLflhoXlrrkiLCJyZXF1aXJlc0F1dGgiOnRydWUsImRlZXBMaW5rIjp0cnVlfSx7ImlkIjoicm91dGUuaGVscCIsInBhdGgiOiIvaGVscCIsInRpdGxlIjoiY29tcG9uZW50LmhlbHAiLCJ0ZXh0Ijoi5biu5Yqp5YaF5a65IiwicmVxdWlyZXNBdXRoIjpmYWxzZSwiZGVlcExpbmsiOmZhbHNlfV19";
final Map<String, Object?> elmosBoundedNavigation =
    jsonDecode(utf8.decode(base64Decode(elmosBoundedNavigationBase64))) as Map<String, Object?>;

typedef ElmosBoundedRoute = Map<String, Object?>;
extension ElmosBoundedRouteFields on ElmosBoundedRoute {
  String get id => this['id']! as String;
  String get path => this['path']! as String;
  String get title => this['title']! as String;
  String get text => this['text']! as String;
  bool get requiresAuth => this['requiresAuth']! as bool;
  bool get deepLink => this['deepLink']! as bool;
}

final List<Object?> elmosBoundedRoutes = elmosBoundedNavigation['routes']! as List<Object?>;
ElmosBoundedRoute elmosRoute(Object? raw) => raw! as ElmosBoundedRoute;
ElmosBoundedRoute get elmosFirstRoute => elmosRoute(elmosBoundedRoutes.first);

ElmosBoundedRoute elmosSelectBoundedRoute(String path) {
  if (elmosBoundedRoutes.isEmpty) throw StateError('bounded navigation requires at least one route');
  final selected = elmosBoundedRoutes.firstWhere((raw) => elmosRoute(raw).path == path, orElse: () => elmosBoundedRoutes.first);
  return elmosRoute(selected);
}

Map<String, Object?> elmosObserveBoundedRoute(String path) {
  final route = elmosSelectBoundedRoute(path);
  final navigation = elmosBoundedNavigation['navigation']! as Map<String, Object?>;
  final render = elmosBoundedNavigation['render']! as Map<String, Object?>;
  return <String, Object?>{
    'routeId': route.id, 'path': route.path, 'title': route.title, 'text': route.text,
    'requiresAuth': route.requiresAuth, 'deepLink': route.deepLink,
    'navigationLabel': navigation['label'], 'mainRole': render['mainRole'],
    'headingLevel': render['headingLevel'],
  };
}

final Map<String, Object?> elmosInitialRender = elmosObserveBoundedRoute(
  elmosFirstRoute.path,
);
