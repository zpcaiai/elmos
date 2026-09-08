function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);
  }
  return Object.is(value, -0) ? 0 : value;
}

export function clamp(value: number, upper: number): number {
    value = _elmosRequireSafeInteger(value);
    upper = _elmosRequireSafeInteger(upper);
    if ((value > upper)) {
        return _elmosRequireSafeInteger(upper);
    }
    if ((value < 0)) {
        return _elmosRequireSafeInteger(0);
    }
    return _elmosRequireSafeInteger(value);
}
