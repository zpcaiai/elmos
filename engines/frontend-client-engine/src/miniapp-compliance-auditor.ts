import { readFileSync, existsSync, readdirSync, lstatSync } from "node:fs";
import { join, relative } from "node:path";
import type { MiniappPlatform } from "./miniapp-types.js";

export type ComplianceSeverity = "INFO" | "WARNING" | "BLOCKING";

export interface ComplianceFinding {
  readonly ruleId: string;
  readonly severity: ComplianceSeverity;
  readonly message: string;
  readonly file: string;
  readonly line?: number;
  readonly column?: number;
  readonly remediation: string;
}

export interface InjectedComplianceShim {
  readonly filename: string;
  readonly content: string;
  readonly purpose: string;
}

export interface MiniappComplianceReport {
  readonly platform: MiniappPlatform;
  readonly auditedFilesCount: number;
  readonly passed: boolean;
  readonly blockingFindingsCount: number;
  readonly warningFindingsCount: number;
  readonly findings: readonly ComplianceFinding[];
  readonly recommendedShims: readonly InjectedComplianceShim[];
}

/**
 * Sensitive capabilities mapping requiring explicit privacy authorizations.
 */
const SENSITIVE_CAPABILITY_MAP: Readonly<Record<string, { desc: string; authKey: string }>> = {
  getLocation: { desc: "Geographic Location", authKey: "scope.userLocation" },
  chooseLocation: { desc: "Geographic Location Picker", authKey: "scope.userLocation" },
  chooseAddress: { desc: "Shipping Address", authKey: "scope.address" },
  chooseInvoiceTitle: { desc: "Invoice Title", authKey: "scope.invoiceTitle" },
  chooseImage: { desc: "Album & Camera", authKey: "scope.camera" },
  chooseMedia: { desc: "Media Picker", authKey: "scope.camera" },
  getClipboardData: { desc: "Clipboard Data Read", authKey: "clipboard" },
  openBluetoothAdapter: { desc: "Bluetooth Low Energy", authKey: "scope.bluetooth" },
  startRecord: { desc: "Microphone Audio Recording", authKey: "scope.record" },
};

/**
 * Audits a miniapp directory for security and app store review compliance.
 */
export function auditMiniappCompliance(
  projectPath: string,
  platform: MiniappPlatform
): MiniappComplianceReport {
  if (!existsSync(projectPath)) {
    throw new Error(`Project path does not exist: ${projectPath}`);
  }

  const findings: ComplianceFinding[] = [];
  let auditedFilesCount = 0;
  const detectedSensitiveApis = new Set<string>();
  let hasPaymentApi = false;

  function scanFile(filePath: string): void {
    const rel = relative(projectPath, filePath);
    const content = readFileSync(filePath, "utf-8");
    const lines = content.split("\n");
    auditedFilesCount += 1;

    // 1. Dynamic script execution check (CRITICAL across all platforms)
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]!;
      const lineNum = i + 1;

      // Check eval()
      if (/\beval\s*\(/u.test(line)) {
        findings.push({
          ruleId: "NO_DYNAMIC_EVAL",
          severity: "BLOCKING",
          message: "Prohibited dynamic code execution via eval() detected. Violates miniapp sandbox security policy.",
          file: rel,
          line: lineNum,
          remediation: "Refactor dynamic evaluation to static AST or pre-compiled logic.",
        });
      }

      // Check new Function()
      if (/\bnew\s+Function\s*\(/u.test(line)) {
        findings.push({
          ruleId: "NO_FUNCTION_CONSTRUCTOR",
          severity: "BLOCKING",
          message: "Prohibited Function() constructor detected. Miniapp platforms reject apps with runtime JS generators.",
          file: rel,
          line: lineNum,
          remediation: "Use static functions or safe dictionary lookups instead of dynamic Function generation.",
        });
      }

      // Check remote script injection in templates
      if (/<script\b[^>]*src\s*=\s*["']https?:\/\//i.test(line)) {
        findings.push({
          ruleId: "NO_REMOTE_SCRIPT_TAG",
          severity: "BLOCKING",
          message: "Prohibited external script tag in miniapp template. Remote executable code violates review policies.",
          file: rel,
          line: lineNum,
          remediation: "Bundle all required code locally within the package.",
        });
      }

      // 2. Sensitive API scanning
      for (const [api, meta] of Object.entries(SENSITIVE_CAPABILITY_MAP)) {
        const pattern = new RegExp(`(?:wx|my|tt|xhs)\\.${api}\\b`, "u");
        if (pattern.test(line)) {
          detectedSensitiveApis.add(api);
        }
      }

      // 3. Virtual payment detection (for iOS platform rules)
      if (/(?:wx|my|tt|xhs)\.requestPayment\b/u.test(line)) {
        hasPaymentApi = true;
        if (/(?:vip|recharge|member|course|token|coin|点券|会员|充值|课程)/iu.test(content)) {
          findings.push({
            ruleId: "IOS_VIRTUAL_PAYMENT_RISK",
            severity: "WARNING",
            message: "Detected payment invocation in proximity to digital goods / subscription keywords. Apple App Store guidelines (3.1.1) forbid iOS miniapp virtual payments without in-app purchase agreement.",
            file: rel,
            line: lineNum,
            remediation: "Gate payment buttons with platform check (e.g. if (platform === 'ios') display custom guidance).",
          });
        }
      }
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
        const ext = entry.name.split(".").pop()?.toLowerCase();
        if (["js", "ts", "wxml", "axml", "ttml", "xhsml", "json"].includes(ext ?? "")) {
          scanFile(fullPath);
        }
      }
    }
  }

  walk(projectPath);

  // 4. Generate privacy compliance shims if sensitive APIs exist
  const recommendedShims: InjectedComplianceShim[] = [];
  if (platform === "wechat" && detectedSensitiveApis.size > 0) {
    findings.push({
      ruleId: "WECHAT_PRIVACY_AUTHORIZATION_REQUIRED",
      severity: "WARNING",
      message: `Detected ${detectedSensitiveApis.size} sensitive privacy API(s) [${Array.from(detectedSensitiveApis).join(", ")}]. WeChat requires active wx.onNeedPrivacyAuthorization listener.`,
      file: "app.js",
      remediation: "Include privacy authorization listener shim to intercept API calls until user confirms agreement.",
    });

    recommendedShims.push({
      filename: "shims/wechat-privacy-guard.js",
      purpose: "Intercepts wx.onNeedPrivacyAuthorization to ensure compliance with WeChat 2024+ privacy policy",
      content: `// WeChat Privacy Authorization Shim
// Generated by ELMOS Frontend & MiniApp Modernization Engine

let privacyResolve = null;

if (typeof wx !== "undefined" && typeof wx.onNeedPrivacyAuthorization === "function") {
  wx.onNeedPrivacyAuthorization((resolve) => {
    privacyResolve = resolve;
    const app = typeof getApp === "function" ? getApp() : null;
    if (app && typeof app.showPrivacyDialog === "function") {
      app.showPrivacyDialog();
    }
  });
}

export function handleUserAgreePrivacy() {
  if (privacyResolve) {
    privacyResolve({ buttonId: "agree-btn", event: "agree" });
    privacyResolve = null;
  }
}

export function handleUserDisagreePrivacy() {
  if (privacyResolve) {
    privacyResolve({ event: "disagree" });
    privacyResolve = null;
  }
}
`,
    });
  }

  const blockingCount = findings.filter(f => f.severity === "BLOCKING").length;
  const warningCount = findings.filter(f => f.severity === "WARNING").length;

  return {
    platform,
    auditedFilesCount,
    passed: blockingCount === 0,
    blockingFindingsCount: blockingCount,
    warningFindingsCount: warningCount,
    findings,
    recommendedShims,
  };
}
