// Hermetic Material Flutter Shim for standalone dart analyzer
abstract class Widget {
  const Widget({Key? key});
}

abstract class StatelessWidget extends Widget {
  const StatelessWidget({Key? key}) : super(key: key);
  Widget build(BuildContext context);
}

abstract class StatefulWidget extends Widget {
  const StatefulWidget({Key? key}) : super(key: key);
  State createState();
}

abstract class State<T extends StatefulWidget> {
  T get widget => throw UnimplementedError();
  BuildContext get context => throw UnimplementedError();
  void setState(void Function() fn) { fn(); }
  Widget build(BuildContext context);
}

class BuildContext {}
class Key {
  final String value;
  const Key(this.value);
}

class Container extends Widget {
  final Widget? child;
  const Container({this.child, Key? key}) : super(key: key);
}

class Text extends Widget {
  final String text;
  const Text(this.text, {Key? key}) : super(key: key);
}

class Column extends Widget {
  final List<Widget> children;
  const Column({this.children = const [], Key? key}) : super(key: key);
}

class ElevatedButton extends Widget {
  final void Function()? onPressed;
  final Widget? child;
  const ElevatedButton({this.onPressed, this.child, Key? key}) : super(key: key);
}
