// Original educational fixture; semantic domain is deliberately bounded.
function quote(amount) {
  if (!Number.isInteger(amount) || amount < 0 || amount > 1000000 || typeof amount !== 'number') {
    throw new Error('INVALID_AMOUNT');
  }
  const subtotal = amount;
  const discount = subtotal >= 10000 ? Math.floor(subtotal / 10) : 0;
  const total = subtotal - discount;
  return {subtotal, discount, total};
}
try { console.log(JSON.stringify(quote(JSON.parse(process.argv[2])))); }
catch (_) { console.log(JSON.stringify({error: 'INVALID_AMOUNT'})); }
