double ratio(double numerator, double denominator, bool invert) {
  if (invert) {
    return denominator / numerator;
  }
  return numerator / denominator;
}
