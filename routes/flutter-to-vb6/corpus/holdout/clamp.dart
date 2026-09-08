int clamp(int value, int upper) {
  if (value > upper) {
    return upper;
  }
  if (value < 0) {
    return 0;
  }
  return value;
}
