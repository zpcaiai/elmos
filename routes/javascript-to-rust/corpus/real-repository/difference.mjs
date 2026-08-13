/**
 * @param {integer} left
 * @param {integer} right
 * @returns {integer}
 */
export function difference(left, right) {
  if (left < right) {
    return 0;
  }
  return left - right;
}
