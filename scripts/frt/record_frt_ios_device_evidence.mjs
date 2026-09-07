#!/usr/bin/env node

/** Record privacy-minimized local iOS install/launch engineering evidence. */

import { createHash, createHmac } from "node:crypto";
import {
  existsSync,
  lstatSync,
  readFileSync,
  readdirSync,
  realpathSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

const repositoryRoot = path.resolve(import.meta.dirname, "../..");
const certificationRoot = path.join(
  repositoryRoot,
  "client-packs/frt-g01-g30-platform/certification",
);
const allowedArguments = new Set([
  "--project",
  "--install-json",
  "--launch-json",
  "--processes-json",
  "--devices-json",
  "--device-id-file",
  "--output",
]);
const requiredArguments = new Set([
  "--project",
  "--install-json",
  "--launch-json",
  "--processes-json",
  "--devices-json",
  "--device-id-file",
]);
const argumentsByName = new Map();

for (let index = 2; index < process.argv.length; index += 2) {
  const name = process.argv[index];
  const value = process.argv[index + 1];
  if (!allowedArguments.has(name) || !value || argumentsByName.has(name)) {
    throw new Error("FRT_IOS_DEVICE_ARGUMENTS_INVALID");
  }
  argumentsByName.set(name, value);
}
if ([...requiredArguments].some((name) => !argumentsByName.has(name))) {
  throw new Error("FRT_IOS_DEVICE_ARGUMENTS_INCOMPLETE");
}

function isBelow(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function isDisposable(candidate) {
  return candidate.startsWith("/private/")
    || candidate.startsWith("/var/")
    || candidate.startsWith("/tmp/");
}

function digest(bytes) {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function safeInput(argumentName) {
  const configured = path.resolve(argumentsByName.get(argumentName));
  const configuredMetadata = lstatSync(configured);
  if (configuredMetadata.isSymbolicLink()) {
    throw new Error("FRT_IOS_DEVICE_RAW_INPUT_MUST_BE_DISPOSABLE_REGULAR_FILE");
  }
  const resolved = realpathSync(configured);
  const metadata = lstatSync(resolved);
  if (!isDisposable(resolved) || !metadata.isFile()) {
    throw new Error("FRT_IOS_DEVICE_RAW_INPUT_MUST_BE_DISPOSABLE_REGULAR_FILE");
  }
  return { path: resolved, bytes: readFileSync(resolved) };
}

function safeJson(argumentName) {
  const input = safeInput(argumentName);
  return { ...input, value: JSON.parse(input.bytes.toString("utf8")) };
}

function requiredText(value, code) {
  if (typeof value !== "string" || value.length === 0 || value.length > 256) {
    throw new Error(code);
  }
  return value;
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
        entries.push({
          path: relative,
          kind: "file",
          byteCount: bytes.byteLength,
          sha256: digest(bytes),
        });
      } else {
        throw new Error("FRT_IOS_APP_SPECIAL_FILE_REJECTED");
      }
    }
  };
  visit(root);
  return entries.sort((left, right) =>
    left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
}

const projectRoot = realpathSync(path.resolve(argumentsByName.get("--project")));
if (!isDisposable(projectRoot) || !lstatSync(projectRoot).isDirectory()) {
  throw new Error("FRT_IOS_DEVICE_PROJECT_MUST_BE_DISPOSABLE");
}
const appRoot = realpathSync(path.join(projectRoot, "build/ios/Profile-iphoneos/Runner.app"));
if (!isBelow(projectRoot, appRoot) || !lstatSync(appRoot).isDirectory()) {
  throw new Error("FRT_IOS_DEVICE_APP_ROOT_INVALID");
}

const outputPath = path.resolve(
  argumentsByName.get("--output")
    ?? path.join(certificationRoot, "ios-physical-device-evidence.json"),
);
if (!isBelow(certificationRoot, outputPath) && !isDisposable(outputPath)) {
  throw new Error("FRT_IOS_DEVICE_OUTPUT_SCOPE_INVALID");
}

const hmacKey = process.env.ELMOS_FRT_DEVICE_ID_HMAC_KEY ?? "";
if (Buffer.byteLength(hmacKey, "utf8") < 32) {
  throw new Error("FRT_IOS_DEVICE_HMAC_KEY_REQUIRED");
}
const deviceIdInput = safeInput("--device-id-file");
const deviceIdentifier = deviceIdInput.bytes.toString("utf8").trim();
if (!/^[A-Za-z0-9._:-]{8,256}$/.test(deviceIdentifier)) {
  throw new Error("FRT_IOS_DEVICE_IDENTITY_INVALID");
}

const install = safeJson("--install-json");
const launch = safeJson("--launch-json");
const processes = safeJson("--processes-json");
const devices = safeJson("--devices-json");
if (install.value.info?.outcome !== "success" || launch.value.info?.outcome !== "success") {
  throw new Error("FRT_IOS_DEVICE_INSTALL_OR_LAUNCH_FAILED");
}

const device = devices.value.result?.devices?.find((item) =>
  item?.hardwareProperties?.udid === deviceIdentifier
  || item?.identifier === deviceIdentifier);
const hardware = device?.hardwareProperties;
const properties = device?.deviceProperties;
const connection = device?.connectionProperties;
if (!device || hardware?.reality !== "physical") {
  throw new Error("FRT_IOS_PHYSICAL_DEVICE_NOT_CONFIRMED");
}

const bundleIdentifier = install.value.result?.installedApplications?.[0]?.bundleIdentifier
  ?? install.value.result?.bundleIdentifier;
const processIdentifier = launch.value.result?.process?.processIdentifier;
const running = processes.value.result?.runningProcesses?.find(
  (entry) => entry.processIdentifier === processIdentifier,
);
if (
  bundleIdentifier !== "io.elmos.frtFlutterRoute"
  || !Number.isInteger(processIdentifier)
  || !running
) {
  throw new Error("FRT_IOS_DEVICE_PROCESS_NOT_CONFIRMED");
}
const executable = path.basename(new URL(requiredText(
  running.executable,
  "FRT_IOS_DEVICE_EXECUTABLE_INVALID",
)).pathname);
if (executable !== "Runner") {
  throw new Error("FRT_IOS_DEVICE_EXECUTABLE_INVALID");
}

const manifest = appManifest(appRoot);
const signed = manifest.some((entry) => entry.path === "_CodeSignature/CodeResources");
if (!signed) {
  throw new Error("FRT_IOS_DEVICE_APP_SIGNATURE_MISSING");
}

const evidence = {
  schemaVersion: "2.0",
  kind: "FRT_IOS_PHYSICAL_DEVICE_LOCAL_EXECUTION",
  generatedAt: new Date().toISOString(),
  routeScope: "bounded-single-public-counter-route-v1",
  device: {
    platform: requiredText(hardware.platform, "FRT_IOS_DEVICE_PLATFORM_INVALID"),
    deviceType: requiredText(hardware.deviceType, "FRT_IOS_DEVICE_TYPE_INVALID"),
    marketingModel: requiredText(hardware.marketingName, "FRT_IOS_DEVICE_MODEL_INVALID"),
    productType: requiredText(hardware.productType, "FRT_IOS_DEVICE_PRODUCT_INVALID"),
    architecture: requiredText(hardware.cpuType?.name, "FRT_IOS_DEVICE_ARCHITECTURE_INVALID"),
    osVersion: requiredText(properties?.osVersionNumber, "FRT_IOS_DEVICE_OS_INVALID"),
    osBuild: requiredText(properties?.osBuildUpdate, "FRT_IOS_DEVICE_BUILD_INVALID"),
    developerMode: requiredText(properties?.developerModeStatus, "FRT_IOS_DEVICE_MODE_INVALID"),
    pairingState: requiredText(connection?.pairingState, "FRT_IOS_DEVICE_PAIRING_INVALID"),
    tunnelState: requiredText(connection?.tunnelState, "FRT_IOS_DEVICE_TUNNEL_INVALID"),
    devicePseudonym: `hmac-sha256:${createHmac("sha256", hmacKey)
      .update(deviceIdentifier)
      .digest("hex")}`,
    reality: "physical",
  },
  application: {
    bundleIdentifier,
    buildMode: "profile",
    signed,
    appManifestSha256: digest(Buffer.from(JSON.stringify(manifest), "utf8")),
    appFileCount: manifest.length,
  },
  execution: {
    installOutcome: install.value.info.outcome,
    launchOutcome: launch.value.info.outcome,
    processConfirmed: true,
    processConfirmedAfterSeconds: 3,
    executable,
  },
  rawEvidenceDigests: {
    deviceInventory: digest(devices.bytes),
    install: digest(install.bytes),
    launch: digest(launch.bytes),
    runningProcesses: digest(processes.bytes),
  },
  privacy: {
    rawDeviceIdentifierPersisted: false,
    deviceNameOrAliasPersisted: false,
    rawProcessIdentifierPersisted: false,
    rawCommandOutputPersisted: false,
    pseudonymization: "HMAC-SHA256 with an external non-persisted key",
  },
  status: "PASSED_LOCAL_EVIDENCE_ONLY",
  boundaries: {
    p0Journeys: "NOT_RUN",
    manualVisualInspection: "NOT_RUN",
    manualAssistiveTechnology: "NOT_RUN",
    customerAcceptance: "NOT_RUN",
    externalDeviceMatrix: "NOT_RUN",
    productionCertification: "NOT_CERTIFIED",
  },
};
writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, { flag: "w" });
process.stdout.write(`${JSON.stringify({
  outputPath,
  sha256: digest(readFileSync(outputPath)),
  status: evidence.status,
  privacy: evidence.privacy,
}, null, 2)}\n`);
