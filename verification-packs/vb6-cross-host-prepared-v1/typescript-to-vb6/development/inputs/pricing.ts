export function calculate(subtotal: number, tax: number): number {
  if (subtotal < 0) {
    return 0;
  }
  return subtotal + tax;
}
