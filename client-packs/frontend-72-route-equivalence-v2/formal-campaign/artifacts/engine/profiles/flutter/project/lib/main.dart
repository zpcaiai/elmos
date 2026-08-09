import 'package:flutter/material.dart';
import 'elmos_bounded_navigation.dart';
import 'elmos_interaction_consumer.dart';

void main() => runApp(const GeneratedApp());

class GeneratedApp extends StatelessWidget {
  const GeneratedApp({this.interactionApiAdapter, this.interactionNativeAdapter, super.key});
  final ElmosApiAdapter? interactionApiAdapter;
  final ElmosNativeAdapter? interactionNativeAdapter;
  @override
  Widget build(BuildContext context) {
    return MaterialApp(title: "ELMOS 有界前端交互验证", initialRoute: elmosFirstRoute.path,
      builder: (context, child) => Column(children: [Expanded(child: child ?? const SizedBox.shrink()), SizedBox(height: 240, child: Material(child: ElmosInteractionPanel(apiAdapter: interactionApiAdapter, nativeAdapter: interactionNativeAdapter)))]),
      routes: { for (final raw in elmosBoundedRoutes) elmosRoute(raw).path: (_) => GeneratedPage(route: elmosRoute(raw)) },
      onUnknownRoute: (_) => MaterialPageRoute<void>(builder: (_) => GeneratedPage(route: elmosFirstRoute)));
  }
}

class GeneratedPage extends StatelessWidget {
  const GeneratedPage({required this.route, super.key});
  final ElmosBoundedRoute route;
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(route.title)),
      drawer: Drawer(
        child: SafeArea(
          child: ListView(
            children: [
              for (final raw in elmosBoundedRoutes)
                ListTile(
                  title: Text(elmosRoute(raw).title),
                  onTap: () => Navigator.of(context).pushReplacementNamed(elmosRoute(raw).path),
                ),
            ],
          ),
        ),
      ),
      body: Center(
        child: Semantics(
          container: true,
          header: true,
          label: '${route.id}|${route.path}|auth:${route.requiresAuth}|deep:${route.deepLink}',
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(route.title, style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 12),
                  Text(route.text),
                  const SizedBox(height: 20),
                  const Text(
                    '生成状态：等待 Android/iOS/Web 设备验证',
                    semanticsLabel: '生成状态，等待设备验证',
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
