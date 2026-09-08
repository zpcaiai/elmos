export function clamp(value: number, upper: number): number {
  if (value > upper) {
    return upper;
  }
  if (value < 0) {
    return 0;
  }
  return value;
}
