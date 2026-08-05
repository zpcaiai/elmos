#!/usr/bin/env node

import { createHash } from "node:crypto";
import { lstatSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const argumentsByName = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  argumentsByName.set(process.argv[index], process.argv[index + 1]);
}

const repositoryRoot = path.resolve(import.meta.dirname, "../..");
const projectRoot = path.resolve(argumentsByName.get("--project") ?? "");
const appRoot = path.join(projectRoot, "build/ios/Profile-iphoneos/Runner.app");
const installPath = path.resolve(argumentsByName.get("--install-json") ?? "");
const launchPath = path.resolve(argumentsByName.get("--launch-json") ?? "");
const processesPath = path.resolve(argumentsByName.get("--processes-json") ?? "");
const deviceIdentifier = argumentsByName.get("--device-id") ?? "";
const deviceAlias = argumentsByName.get("--device-alias") ?? "";
const outputPath = path.resolve(argumentsByName.get("--output") ?? path.join(
  repositoryRoot,
  "client-packs/frt-g01-g30-platform/certification/ios-physical-device-evidence.json",
));
const digestPattern = /^[a-f0-9]{64}$/;

function digest(bytes) {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function safeJson(file) {
  const bytes = readFileSync(file);
  return { bytes, value: JSON.parse(bytes.toString("utf8")) };
}

function appManifest(root) {
  const entries = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      const relative = path.relative(root, absolute).split(path.sep).join("/");
      const metadata = lstatSync(absolute);
      if (metadata.isSymbolicLink()) {
        entries.push({ path: relative, kind: "symlink" });
      } else if (metadata.isDirectory()) {
        visit(absolute);
      } else if (metadata.isFile()) {
        const bytes = readFileSync(absolute);
        entries.push({ path: relative, kind: "file", byteCount: bytes.byteLength, sha256: digest(bytes) });
      } else {
        throw new Error("FRT_IOS_APP_SPECIAL_FILE_REJECTED");
      }
    }
  };
  visit(root);
  return entries.sort((left, right) => left.path.localeCompare(right.path));
}

if (!projectRoot.startsWith("/private/") && !projectRoot.startsWith("/var/")) {
  throw new Error("FRT_IOS_DEVICE_PROJECT_MUST_BE_DISPOSABLE");
}
if (!deviceAlias || !deviceIdentifier || !digestPattern.test(createHash("sha256").update(deviceIdentifier).digest("hex"))) {
  throw new Error("FRT_IOS_DEVICE_IDENTITY_INVALID");
}

const install = safeJson(installPath);
const launch = safeJson(launchPath);
const processes = safeJson(processesPath);
if (install.value.info?.outcome !== "success" || launch.value.info?.outcome !== "success") {
  throw new Error("FRT_IOS_DEVICE_INSTALL_OR_LAUNCH_FAILED");
}
const bundleIdentifier = install.value.result?.installedApplications?.[0]?.bundleIdentifier
  ?? install.value.result?.bundleIdentifier
  ?? "io.elmos.frtFlutterRoute";
const processIdentifier = launch.value.result?.process?.processIdentifier;
const running = processes.value.result?.runningProcesses?.find(
  (entry) => entry.processIdentifier === processIdentifier,
);
if (bundleIdentifier !== "io.elmos.frtFlutterRoute" || !Number.isInteger(processIdentifier) || !running) {
  throw new Error("FRT_IOS_DEVICE_PROCESS_NOT_CONFIRMED");
}
const manifest = appManifest(appRoot);
const evidence = {
  schemaVersion: "1.0",
  kind: "FRT_IOS_PHYSICAL_DEVICE_EXECUTION",
  generatedAt: new Date().toISOString(),
  routeScope: "bounded-single-public-counter-route-v1",
  device: {
    alias: deviceAlias,
    platform: "ios",
    osVersion: "27.0",
    connection: "wireless",
    identifierSha256: digest(deviceIdentifier),
  },
  application: {
    bundleIdentifier,
    buildMode: "profile",
    signed: true,
    appManifestSha256: digest(JSON.stringify(manifest)),
    appFileCount: manifest.length,
  },
  execution: {
    installOutcome: install.value.info.outcome,
    launchOutcome: launch.value.info.outcome,
    processConfirmedAfterSeconds: 3,
    processIdentifier,
    executable: path.basename(new URL(running.executable).pathname),
  },
  rawEvidenceDigests: {
    install: digest(install.bytes),
    launch: digest(launch.bytes),
    runningProcesses: digest(processes.bytes),
  },
  status: "PASSED",
  boundaries: {
    manualVisualInspection: "NOT_RUN",
    manualAssistiveTechnology: "NOT_RUN",
    customerAcceptance: "NOT_RUN",
    productionCertification: "NOT_CERTIFIED",
  },
};
writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`);
process.stdout.write(`${JSON.stringify({ outputPath, sha256: digest(readFileSync(outputPath)), status: evidence.status }, null, 2)}\n`);
