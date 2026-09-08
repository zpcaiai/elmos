function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);
  }
  return Object.is(value, -0) ? 0 : value;
}

export function calculate(subtotal: number, tax: number): number {
    subtotal = _elmosRequireSafeInteger(subtotal);
    tax = _elmosRequireSafeInteger(tax);
    if ((subtotal < 0)) {
        return _elmosRequireSafeInteger(0);
    }
    return _elmosRequireSafeInteger(_elmosRequireSafeInteger(subtotal + tax));
}
