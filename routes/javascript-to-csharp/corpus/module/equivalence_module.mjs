/**
 * @param {integer} subtotal
 * @param {integer} tax
 * @returns {integer}
 */
export function calculate(subtotal, tax) {
  if (subtotal < 0) { return 0; }
  return subtotal + tax;
}

/**
 * @param {integer} value
 * @param {integer} minimum
 * @param {integer} maximum
 * @returns {integer}
 */
export function clamp(value, minimum, maximum) {
  if (value < minimum) { return minimum; }
  if (value > maximum) { return maximum; }
  return value;
}

/**
 * @param {integer} left
 * @param {integer} right
 * @returns {integer}
 */
export function difference(left, right) {
  return left - right;
}

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
 * @param {boolean} left
 * @param {boolean} right
 * @returns {boolean}
 */
export function both(left, right) {
  return left && right;
}
