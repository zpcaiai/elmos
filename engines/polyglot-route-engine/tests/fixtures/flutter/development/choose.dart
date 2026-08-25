int choose(int left, int right, bool doubleIt) {
  final int total = left + right;
  if (doubleIt) {
    return total * 2;
  } else {
    return total % 3;
  }
}
