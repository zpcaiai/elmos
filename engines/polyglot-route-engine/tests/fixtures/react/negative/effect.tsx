export function readValue(value: number): number {
  useEffect(() => value, []);
  return value;
}
