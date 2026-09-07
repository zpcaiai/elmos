/**
 * Runs the target project's REAL build so that "the output runs" is a
 * checked fact rather than a claim.
 *
 * Only frameworks whose toolchain is obtainable as plain npm packages can
 * be verified here. For the rest the result is NOT_VERIFIABLE_HERE with
 * the specific missing toolchain named -- that is reported, never quietly
 * folded into a pass.
 */
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { Framework } from "./models";

export interface BuildVerification {
  status: "PASSED" | "FAILED" | "NOT_VERIFIABLE_HERE";
  command: string | null;
  reason: string | null;
  output: string | null;
}

/** Toolchains that cannot be run from npm alone. Naming the exact missing
 * dependency is the point: a reader must be able to tell what would have
 * to be installed to turn this into real evidence. */
const UNVERIFIABLE: Partial<Record<Framework, string>> = {
  "react-native": "requires the Expo/Metro bundler plus an Android or iOS simulator",
  miniprogram: "requires the official WeChat Developer Tools (no public headless CLI)",
  arkui: "requires HarmonyOS DevEco Studio and the ArkTS compiler",
  angular: "requires an Angular CLI workspace with platform-server for a real build",
};

function run(command: string, args: string[], cwd: string): { ok: boolean; output: string } {
  try {
    const output = execFileSync(command, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 10 * 60_000 });
    return { ok: true, output };
  } catch (error) {
    const err = error as { stdout?: string; stderr?: string; message?: string };
    return { ok: false, output: [err.stdout, err.stderr, err.message].filter(Boolean).join("\n") };
  }
}

export function verifyBuild(destination: string, framework: Framework, options: { install?: boolean } = {}): BuildVerification {
  const unverifiable = UNVERIFIABLE[framework];
  if (unverifiable) {
    return { status: "NOT_VERIFIABLE_HERE", command: null, reason: `${framework} ${unverifiable}`, output: null };
  }
  if (framework === "flutter" && !fs.existsSync(path.join(destination, "pubspec.yaml"))) {
    return { status: "NOT_VERIFIABLE_HERE", command: null, reason: "Flutter target has no generated pubspec.yaml to analyze", output: null };
  }
  if (!fs.existsSync(path.join(destination, "package.json"))) {
    if (framework === "flutter" && fs.existsSync(path.join(destination, "pubspec.yaml"))) {
      const pub = run("flutter", ["pub", "get"], destination);
      if (!pub.ok) return { status: "FAILED", command: "flutter pub get", reason: "Flutter dependencies could not be resolved", output: pub.output.slice(-4000) };
      const analyze = run("flutter", ["analyze", "--no-fatal-infos"], destination);
      return {
        status: analyze.ok ? "PASSED" : "FAILED",
        command: "flutter pub get && flutter analyze --no-fatal-infos",
        reason: analyze.ok ? "Dart/Flutter static analysis passed; device runtime was not exercised" : "the generated Flutter project did not pass Dart analysis",
        output: analyze.output.slice(-4000),
      };
    }
    return { status: "FAILED", command: null, reason: "no package.json was written to the destination", output: null };
  }

  if (options.install !== false) {
    const install = run("npm", ["install", "--no-audit", "--no-fund"], destination);
    if (!install.ok) {
      return { status: "FAILED", command: "npm install", reason: "dependency installation failed", output: install.output.slice(-4000) };
    }
  }

  const build = run("npx", ["vite", "build"], destination);
  return {
    status: build.ok ? "PASSED" : "FAILED",
    command: "npx vite build",
    reason: build.ok ? null : "the generated project did not build",
    output: build.output.slice(-4000),
  };
}
