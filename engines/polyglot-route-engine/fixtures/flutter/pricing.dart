int calculate(int subtotal, int tax) {
  if (subtotal < 0) {
    return 0;
  }
  return subtotal + tax;
}
