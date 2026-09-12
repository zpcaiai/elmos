function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);
  }
  return Object.is(value, -0) ? 0 : value;
}

export function difference(left: number, right: number): number {
    left = _elmosRequireSafeInteger(left);
    right = _elmosRequireSafeInteger(right);
    if ((left < right)) {
        return _elmosRequireSafeInteger(0);
    }
    return _elmosRequireSafeInteger(_elmosRequireSafeInteger(left - right));
}
