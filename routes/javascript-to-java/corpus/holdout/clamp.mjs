/**
 * @param {integer} value
 * @param {integer} upper
 * @returns {integer}
 */
export function clamp(value, upper) {
  if (value > upper) {
    return upper;
  }
  if (value < 0) {
    return 0;
  }
  return value;
}
