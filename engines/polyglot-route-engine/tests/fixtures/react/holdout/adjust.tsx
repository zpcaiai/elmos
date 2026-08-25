export function adjust(value: number, active: boolean): number {
  if (active && value > 0) {
    return value + 2;
  }
  return value - 1;
}
