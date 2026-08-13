/**
 * @param {integer} subtotal
 * @param {integer} tax
 * @returns {integer}
 */
export function calculate(subtotal, tax) {
  if (subtotal < 0) {
    return 0;
  }
  return subtotal + tax;
}
