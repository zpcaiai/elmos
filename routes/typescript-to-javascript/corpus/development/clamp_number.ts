export function clampNumber(value: number, minimum: number, maximum: number): number {
  if (value < minimum) { return minimum; }
  if (value > maximum) { return maximum; }
  return value;
}
