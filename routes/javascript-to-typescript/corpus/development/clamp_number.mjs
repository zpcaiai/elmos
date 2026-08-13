/**
 * @param {number} value
 * @param {number} minimum
 * @param {number} maximum
 * @returns {number}
 */
export function clampNumber(value, minimum, maximum) {
  if (value < minimum) { return minimum; }
  if (value > maximum) { return maximum; }
  return value;
}
