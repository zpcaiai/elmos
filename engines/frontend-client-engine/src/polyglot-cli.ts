import { readFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { analyzeTypedFunction } from "./polyglot.js";

const [, , sourceArgument, functionName] = process.argv;
if (!sourceArgument || !functionName) {
  process.stderr.write("usage: polyglot-cli <source> <function>\n");
  process.exitCode = 2;
} else {
  const sourcePath = resolve(sourceArgument);
  const source = readFileSync(sourcePath, "utf8");
  process.stdout.write(JSON.stringify(analyzeTypedFunction(source, basename(sourcePath), functionName)) + "\n");
}
