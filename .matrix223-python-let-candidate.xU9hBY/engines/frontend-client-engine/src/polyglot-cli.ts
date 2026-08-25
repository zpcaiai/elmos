import { readFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { analyzeTypedFunction, inventoryTypedModule } from "./polyglot.js";

const [, , sourceArgument, functionName] = process.argv;
if (!sourceArgument || !functionName) {
  process.stderr.write("usage: polyglot-cli <source> <function>\n");
  process.exitCode = 2;
} else {
  const sourcePath = resolve(sourceArgument);
  const source = readFileSync(sourcePath, "utf8");
  const result = functionName === "--inventory"
    ? inventoryTypedModule(source, basename(sourcePath))
    : analyzeTypedFunction(source, basename(sourcePath), functionName);
  process.stdout.write(JSON.stringify(result) + "\n");
}
