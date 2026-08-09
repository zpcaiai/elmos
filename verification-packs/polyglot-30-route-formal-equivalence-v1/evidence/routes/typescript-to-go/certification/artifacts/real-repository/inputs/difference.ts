export function difference(left: number, right: number): number {
  if (left < right) {
    return 0;
  }
  return left - right;
}
