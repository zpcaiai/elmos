import { useEffect } from 'react';
import { useCart } from './store';

export function App() {
  const quantity = useCart((s) => s.quantity);
  const add = useCart((s) => s.add);

  useEffect(() => {
    const controller = new AbortController();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>Product</h1>
      <button onClick={add}>Add to cart</button>
      <output aria-label="Cart quantity">{quantity}</output>
    </main>
  );
}
