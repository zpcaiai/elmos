int _elmosInIntegerRange(BigInt value) {
  final minimum = BigInt.from(-9223372036854775808);
  final maximum = BigInt.from(9223372036854775807);
  if (value < minimum || value > maximum) {
    throw RangeError('ELMOS_INTEGER_OVERFLOW');
  }
  return value.toInt();
}

int _elmosCheckedSub(int left, int right) {
  return _elmosInIntegerRange(BigInt.from(left) - BigInt.from(right));
}

int difference(int left, int right) {
    if ((left < right)) {
        return 0;
    }
    return _elmosCheckedSub(left, right);
}
