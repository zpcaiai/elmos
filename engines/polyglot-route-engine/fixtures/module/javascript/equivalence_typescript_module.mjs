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

/**
 * @param {number} value
 * @param {number} minimum
 * @returns {number}
 */
export function lowerNumber(value, minimum) {
  if (value < minimum) { return minimum; }
  return value;
}

/**
 * @param {number} value
 * @param {number} maximum
 * @returns {number}
 */
export function upperNumber(value, maximum) {
  if (value > maximum) { return maximum; }
  return value;
}

/**
 * @param {string} left
 * @param {string} right
 * @returns {boolean}
 */
export function sameString(left, right) {
  return left === right;
}

/**
 * @param {string} left
 * @param {string} right
 * @returns {string}
 */
export function concatString(left, right) {
  return left + right;
}

/**
 * @param {boolean} left
 * @param {boolean} right
 * @returns {boolean}
 */
export function both(left, right) {
  return left && right;
}
