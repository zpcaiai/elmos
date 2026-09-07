import { useState } from "react";

export function Counter(): number {
  const [count] = useState(0);
  return count;
}
