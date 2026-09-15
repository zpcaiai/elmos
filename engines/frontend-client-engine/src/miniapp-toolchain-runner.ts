import { existsSync, lstatSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import type { MiniappPlatform } from "./miniapp-types.js";

export type ToolchainAction = "build" | "preview" | "upload" | "analyze";
export type ToolchainStatus = "PASSED" | "FAILED" | "NOT_RUN" | "CREDENTIAL_REQUIRED" | "BINARY_MISSING";

export interface WechatCiConfig {
  readonly platform: "wechat";
  readonly appid: string;
  readonly projectPath: string;
  readonly privateKeyPath?: string | undefined;
  readonly privateKeyContent?: string | undefined;
  readonly version?: string | undefined;
  readonly desc?: string | undefined;
  readonly qrcodeFormat?: "terminal" | "base64" | "image" | undefined;
  readonly qrcodeOutputDest?: string | undefined;
  readonly compilesettings?: {
    readonly es6?: boolean | undefined;
    readonly es7?: boolean | undefined;
    readonly minify?: boolean | undefined;
    readonly autoPrefixWXSS?: boolean | undefined;
  } | undefined;
}

export interface AlipayMinidevConfig {
  readonly platform: "alipay";
  readonly appid: string;
  readonly projectPath: string;
  readonly toolId?: string | undefined;
  readonly privateKeyPath?: string | undefined;
  readonly version?: string | undefined;
  readonly clientType?: "alipay" | undefined;
}

export interface DouyinCiConfig {
  readonly platform: "douyin";
  readonly appid: string;
  readonly projectPath: string;
  readonly email?: string | undefined;
  readonly password?: string | undefined;
  readonly token?: string | undefined;
  readonly version?: string | undefined;
  readonly desc?: string | undefined;
}

export interface XiaohongshuCiConfig {
  readonly platform: "xiaohongshu";
  readonly appid: string;
  readonly projectPath: string;
  readonly appSecret?: string | undefined;
  readonly version?: string | undefined;
}

export type MiniappToolchainConfig =
  | WechatCiConfig
  | AlipayMinidevConfig
  | DouyinCiConfig
  | XiaohongshuCiConfig;

export interface BundleMetrics {
  readonly totalBytes: number;
  readonly mainPackageBytes: number;
  readonly subpackageBytes: Readonly<Record<string, number>>;
  readonly assetBytes: number;
  readonly fileCount: number;
}

export interface ToolchainExecutionRequest {
  readonly action: ToolchainAction;
  readonly config: MiniappToolchainConfig;
  readonly dryRun?: boolean | undefined;
  readonly timeoutMs?: number | undefined;
}

export interface ToolchainExecutionResult {
  readonly platform: MiniappPlatform;
  readonly action: ToolchainAction;
  readonly status: ToolchainStatus;
  readonly durationMs: number;
  readonly exitCode: number;
  readonly command: string;
  readonly stdout: string;
  readonly stderr: string;
  readonly bundleMetrics?: BundleMetrics | undefined;
  readonly previewOutput?: string | undefined;
  readonly uploadedVersion?: string | undefined;
  readonly errors: readonly string[];
  readonly diagnostic?: string | undefined;
}

/**
 * Analyzes file sizes and package distribution of a generated miniapp directory.
 */
export function analyzeMiniappBundle(projectPath: string): BundleMetrics {
  if (!existsSync(projectPath)) {
    throw new Error(`Project path does not exist: ${projectPath}`);
  }

  let totalBytes = 0;
  let assetBytes = 0;
  let fileCount = 0;
  let mainPackageBytes = 0;
  const subpackageBytes: Record<string, number> = {};

  // Check app.json for declared subpackages
  const appJsonPath = join(projectPath, "app.json");
  const subpackageRoots = new Set<string>();
  if (existsSync(appJsonPath)) {
    try {
      const appJson = JSON.parse(readFileSync(appJsonPath, "utf-8"));
      if (Array.isArray(appJson.subpackages)) {
        for (const sub of appJson.subpackages) {
          if (typeof sub.root === "string") {
            subpackageRoots.add(sub.root.replace(/^\/+|\/+$/g, ""));
          }
        }
      }
      if (Array.isArray(appJson.subPackages)) {
        for (const sub of appJson.subPackages) {
          if (typeof sub.root === "string") {
            subpackageRoots.add(sub.root.replace(/^\/+|\/+$/g, ""));
          }
        }
      }
    } catch {
      // Ignored if app.json parsing fails; will treat as flat
    }
  }

  function walk(currentDir: string): void {
    const entries = readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = join(currentDir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "node_modules" && entry.name !== ".git") {
          walk(fullPath);
        }
      } else if (entry.isFile()) {
        const stat = lstatSync(fullPath);
        const bytes = stat.size;
        totalBytes += bytes;
        fileCount += 1;

        const relPath = relative(projectPath, fullPath);
        const ext = entry.name.includes(".") ? entry.name.split(".").pop()?.toLowerCase() : "";
        if (["png", "jpg", "jpeg", "gif", "svg", "webp", "mp3", "mp4", "wav"].includes(ext ?? "")) {
          assetBytes += bytes;
        }

        // Determine if file belongs to a subpackage
        let inSubpackage = false;
        for (const root of subpackageRoots) {
          if (relPath.startsWith(root + "/") || relPath.startsWith(root + "\\")) {
            subpackageBytes[root] = (subpackageBytes[root] ?? 0) + bytes;
            inSubpackage = true;
            break;
          }
        }
        if (!inSubpackage) {
          mainPackageBytes += bytes;
        }
      }
    }
  }

  walk(projectPath);

  return {
    totalBytes,
    mainPackageBytes,
    subpackageBytes,
    assetBytes,
    fileCount,
  };
}

/**
 * Builds the safe invocation command line without exposing raw secrets.
 */
export function buildToolchainCliCommand(request: ToolchainExecutionRequest): {
  cmd: string;
  args: string[];
  displayCommand: string;
  missingCredentials: string[];
} {
  const { action, config } = request;
  const missingCredentials: string[] = [];

  if (action === "analyze") {
    return {
      cmd: "analyze",
      args: [config.projectPath],
      displayCommand: `analyze ${config.projectPath}`,
      missingCredentials: [],
    };
  }

  if (config.platform === "wechat") {
    const args: string[] = [action];
    args.push("--project-path", config.projectPath);
    args.push("--appid", config.appid);

    if (config.privateKeyPath) {
      args.push("--pkp", config.privateKeyPath);
    } else {
      missingCredentials.push("privateKeyPath");
    }

    if (action === "upload") {
      args.push("--version", config.version ?? "1.0.0");
      args.push("--desc", config.desc ?? "Automated conversion release");
    } else if (action === "preview") {
      args.push("--format", config.qrcodeFormat ?? "terminal");
      if (config.qrcodeOutputDest) {
        args.push("--output", config.qrcodeOutputDest);
      }
    }

    return {
      cmd: "miniprogram-ci",
      args,
      displayCommand: `miniprogram-ci ${args.map(a => a.includes(" ") ? `"${a}"` : a).join(" ")}`,
      missingCredentials,
    };
  }

  if (config.platform === "alipay") {
    const args: string[] = [action];
    args.push("--project", config.projectPath);
    args.push("--app-id", config.appid);

    if (config.toolId) {
      args.push("--tool-id", config.toolId);
    } else {
      missingCredentials.push("toolId");
    }

    if (config.privateKeyPath) {
      args.push("--private-key", config.privateKeyPath);
    } else {
      missingCredentials.push("privateKeyPath");
    }

    if (action === "upload") {
      args.push("--version", config.version ?? "1.0.0");
    }

    return {
      cmd: "minidev",
      args,
      displayCommand: `minidev ${args.map(a => a.includes(" ") ? `"${a}"` : a).join(" ")}`,
      missingCredentials,
    };
  }

  if (config.platform === "douyin") {
    const args: string[] = [action];
    args.push("--entry", config.projectPath);
    args.push("--appid", config.appid);

    if (config.token) {
      args.push("--token", "[REDACTED_TOKEN]");
    } else if (config.email && config.password) {
      args.push("--email", config.email);
      args.push("--password", "[REDACTED_PASSWORD]");
    } else {
      missingCredentials.push("token or email/password");
    }

    if (action === "upload") {
      args.push("--version", config.version ?? "1.0.0");
      args.push("--desc", config.desc ?? "Automated upload");
    }

    return {
      cmd: "tt",
      args,
      displayCommand: `tt ${args.join(" ")}`,
      missingCredentials,
    };
  }

  // Xiaohongshu
  const args = [action, "--project", config.projectPath, "--appid", config.appid];
  if (!config.appSecret) {
    missingCredentials.push("appSecret");
  }
  return {
    cmd: "xhs-dev",
    args,
    displayCommand: `xhs-dev ${args.join(" ")}`,
    missingCredentials,
  };
}

/**
 * Executes or dry-runs official miniapp toolchain operations.
 */
export async function executeMiniappToolchain(
  request: ToolchainExecutionRequest
): Promise<ToolchainExecutionResult> {
  const t0 = Date.now();
  const { action, config, dryRun = false } = request;
  const errors: string[] = [];

  // 1. Verify project exists
  if (!existsSync(config.projectPath)) {
    return {
      platform: config.platform,
      action,
      status: "FAILED",
      durationMs: Date.now() - t0,
      exitCode: 1,
      command: "",
      stdout: "",
      stderr: `Project path does not exist: ${config.projectPath}`,
      errors: [`Project path does not exist: ${config.projectPath}`],
    };
  }

  // 2. Analyze bundle metrics
  let bundleMetrics: BundleMetrics | undefined;
  try {
    bundleMetrics = analyzeMiniappBundle(config.projectPath);
  } catch (err: any) {
    errors.push(`Failed to calculate bundle metrics: ${err.message}`);
  }

  // 3. Compute CLI invocation specs
  const { cmd, args, displayCommand, missingCredentials } = buildToolchainCliCommand(request);

  // 4. Handle Dry-Run mode
  if (dryRun) {
    const isCredentialBlocked = missingCredentials.length > 0;
    const status: ToolchainStatus = isCredentialBlocked ? "CREDENTIAL_REQUIRED" : "PASSED";
    const stdout = [
      `[DRY_RUN] Platform: ${config.platform}, Action: ${action}`,
      `[DRY_RUN] Command: ${displayCommand}`,
      `[DRY_RUN] Project: ${config.projectPath}`,
      bundleMetrics ? `[DRY_RUN] Bundle Total: ${(bundleMetrics.totalBytes / 1024).toFixed(2)} KiB (Main: ${(bundleMetrics.mainPackageBytes / 1024).toFixed(2)} KiB, Files: ${bundleMetrics.fileCount})` : "",
      isCredentialBlocked ? `[DRY_RUN] Missing required credentials for official execution: ${missingCredentials.join(", ")}` : "[DRY_RUN] Credentials validated.",
    ].filter(Boolean).join("\n");

    return {
      platform: config.platform,
      action,
      status,
      durationMs: Date.now() - t0,
      exitCode: isCredentialBlocked ? 2 : 0,
      command: displayCommand,
      stdout,
      stderr: isCredentialBlocked ? `Missing required credentials: ${missingCredentials.join(", ")}` : "",
      bundleMetrics,
      previewOutput: action === "preview" ? "[DRY_RUN_PREVIEW_MOCK_QR]" : undefined,
      uploadedVersion: action === "upload" ? (config as any).version ?? "1.0.0" : undefined,
      errors: isCredentialBlocked ? [`Missing required credentials: ${missingCredentials.join(", ")}`] : [],
      diagnostic: isCredentialBlocked
        ? `To run real official toolchain execution, provide: ${missingCredentials.join(", ")}.`
        : undefined,
    };
  }

  // 5. Fail-closed if real execution requested without credentials
  if (missingCredentials.length > 0) {
    return {
      platform: config.platform,
      action,
      status: "CREDENTIAL_REQUIRED",
      durationMs: Date.now() - t0,
      exitCode: 2,
      command: displayCommand,
      stdout: "",
      stderr: `Refusing real execution: missing required credentials [${missingCredentials.join(", ")}]. Non-self-certification contract prohibits faking credentials.`,
      bundleMetrics,
      errors: [`Missing required credentials: ${missingCredentials.join(", ")}`],
      diagnostic: `Real platform ${action} requires authentic developer credentials configured in host broker.`,
    };
  }

  // 5.1 If action is analyze, return bundle metrics without spawning child process
  if (action === "analyze") {
    return {
      platform: config.platform,
      action: "analyze",
      status: "PASSED",
      durationMs: Date.now() - t0,
      exitCode: 0,
      command: displayCommand,
      stdout: bundleMetrics
        ? `[ANALYZE] Total: ${(bundleMetrics.totalBytes / 1024).toFixed(2)} KiB across ${bundleMetrics.fileCount} files.`
        : "[ANALYZE] Complete.",
      stderr: "",
      bundleMetrics,
      errors: [],
    };
  }

  // 6. Attempt real execution via child_process
  try {
    const child = spawnSync(cmd, args, {
      timeout: request.timeoutMs ?? 60000,
      encoding: "utf-8",
      cwd: config.projectPath,
    });

    if (child.error) {
      if ((child.error as any).code === "ENOENT") {
        return {
          platform: config.platform,
          action,
          status: "BINARY_MISSING",
          durationMs: Date.now() - t0,
          exitCode: 127,
          command: displayCommand,
          stdout: child.stdout || "",
          stderr: `Official toolchain binary '${cmd}' not found on system PATH. Please install it (e.g. npm i -g miniprogram-ci / minidev).`,
          bundleMetrics,
          errors: [`Toolchain executable '${cmd}' not found`],
          diagnostic: `Install '${cmd}' globally or in environment to enable official platform CI.`,
        };
      }
      return {
        platform: config.platform,
        action,
        status: "FAILED",
        durationMs: Date.now() - t0,
        exitCode: child.status ?? 1,
        command: displayCommand,
        stdout: child.stdout || "",
        stderr: child.error.message,
        bundleMetrics,
        errors: [child.error.message],
      };
    }

    const passed = child.status === 0;
    return {
      platform: config.platform,
      action,
      status: passed ? "PASSED" : "FAILED",
      durationMs: Date.now() - t0,
      exitCode: child.status ?? 0,
      command: displayCommand,
      stdout: child.stdout || "",
      stderr: child.stderr || "",
      bundleMetrics,
      previewOutput: action === "preview" ? child.stdout : undefined,
      uploadedVersion: action === "upload" && passed ? (config as any).version ?? "1.0.0" : undefined,
      errors: passed ? [] : [child.stderr || `Toolchain exited with code ${child.status}`],
    };
  } catch (err: any) {
    return {
      platform: config.platform,
      action,
      status: "FAILED",
      durationMs: Date.now() - t0,
      exitCode: 1,
      command: displayCommand,
      stdout: "",
      stderr: err.message,
      bundleMetrics,
      errors: [err.message],
    };
  }
}
