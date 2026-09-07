function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);
  }
  return value;
}

export function difference(left: number, right: number): number {
    _elmosRequireSafeInteger(left);
    _elmosRequireSafeInteger(right);
    if ((left < right)) {
        return _elmosRequireSafeInteger(0);
    }
    return _elmosRequireSafeInteger(_elmosRequireSafeInteger(left - right));
}
