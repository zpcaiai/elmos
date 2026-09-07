export function clampNumber(value: number, minimum: number, maximum: number): number {
  if (value < minimum) { return minimum; }
  if (value > maximum) { return maximum; }
  return value;
}

export function lowerNumber(value: number, minimum: number): number {
  if (value < minimum) { return minimum; }
  return value;
}

export function upperNumber(value: number, maximum: number): number {
  if (value > maximum) { return maximum; }
  return value;
}

export function sameString(left: string, right: string): boolean {
  return left === right;
}

export function concatString(left: string, right: string): string {
  return left + right;
}

export function both(left: boolean, right: boolean): boolean {
  return left && right;
}
