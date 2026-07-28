import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { dirname, resolve, sep } from "node:path";
import { generateUiProject } from "./project-generation.js";
import type { UiProjectGenerationRequest } from "./project-types.js";

function usage(): never {
  process.stderr.write("usage: project-cli <request.json> <output-directory>\n");
  process.exit(2);
}

const [, , requestArgument, outputArgument, ...options] = process.argv;
if (!requestArgument || !outputArgument) usage();
if (options.length > 0) usage();

const requestPath = resolve(requestArgument);
const outputPath = resolve(outputArgument);
if (outputPath === resolve("/") || outputPath === resolve(process.cwd())) {
  throw new Error("output directory must be a dedicated child directory");
}
if (existsSync(outputPath) && readdirSync(outputPath).length > 0) {
  throw new Error("output directory must be absent or empty");
}

const request = JSON.parse(readFileSync(requestPath, "utf8")) as UiProjectGenerationRequest;
const project = generateUiProject(request);
mkdirSync(outputPath, { recursive: true });
for (const [relativePath, content] of Object.entries(project.files)) {
  const target = resolve(outputPath, relativePath);
  if (!target.startsWith(`${outputPath}${sep}`)) throw new Error("generated file escaped output directory");
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content, { encoding: "utf8", flag: "wx" });
}
chmodSync(resolve(outputPath, "scripts/verify.sh"), 0o755);

writeFileSync(
  resolve(outputPath, "materialization-report.json"),
  `${JSON.stringify({
    schemaVersion: "1.0",
    projectId: project.projectId,
    outputPath,
    generatedFileCount: Object.keys(project.files).length,
    lockfile: "NOT_RUN",
    targetBuild: "NOT_RUN",
    targetStartup: "NOT_RUN",
    browserOrDeviceJourney: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  }, null, 2)}\n`,
  { encoding: "utf8", flag: "wx" },
);
process.stdout.write(`${JSON.stringify({
  projectId: project.projectId,
  outputPath,
  generatedFileCount: Object.keys(project.files).length + 1,
  lockfile: "NOT_RUN",
  certification: "NOT_CERTIFIED",
})}\n`);
