import { clamp as _elmosHarnessSubject } from "./clamp.js";
function _elmosHarnessFP64(value: number): string {
  const bytes = new ArrayBuffer(8);
  const view = new DataView(bytes);
  view.setFloat64(0, value, false);
  return view.getBigUint64(0, false).toString(16).padStart(16, "0");
}
function _elmosHarnessHexUTF8(value: string): string {
  return Array.from(new TextEncoder().encode(value), byte => byte.toString(16).padStart(2, "0")).join("");
}
const actual0 = _elmosHarnessSubject(20, 10);
const expected0 = 10;
if (!Number.isFinite(actual0) || !Object.is(actual0, expected0)) throw new Error("case 0");
console.log("ELMOS_OBSERVATION\t0\tfp64-hex\t" + _elmosHarnessFP64(actual0));
const actual1 = _elmosHarnessSubject(-2, 10);
const expected1 = 0;
if (!Number.isFinite(actual1) || !Object.is(actual1, expected1)) throw new Error("case 1");
console.log("ELMOS_OBSERVATION\t1\tfp64-hex\t" + _elmosHarnessFP64(actual1));
const actual2 = _elmosHarnessSubject(7, 10);
const expected2 = 7;
if (!Number.isFinite(actual2) || !Object.is(actual2, expected2)) throw new Error("case 2");
console.log("ELMOS_OBSERVATION\t2\tfp64-hex\t" + _elmosHarnessFP64(actual2));
