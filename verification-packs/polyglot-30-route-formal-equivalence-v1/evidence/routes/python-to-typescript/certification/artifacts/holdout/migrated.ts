function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);
  }
  return value;
}

export function clamp(value: number, upper: number): number {
    _elmosRequireSafeInteger(value);
    _elmosRequireSafeInteger(upper);
    if ((value > upper)) {
        return _elmosRequireSafeInteger(upper);
    }
    if ((value < 0)) {
        return _elmosRequireSafeInteger(0);
    }
    return _elmosRequireSafeInteger(value);
}
