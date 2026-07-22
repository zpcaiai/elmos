import type { FrontendMigrationPlan, MigrationStep, TargetProfile, WorkspaceInventory } from "./domain.js";

function step(stepId: string, type: string, dependsOn: readonly string[], automatic: boolean,
              requiredRunner: string, acceptanceGates: readonly string[]): MigrationStep {
  return { stepId, type, dependsOn, automatic, requiredRunner, acceptanceGates };
}

function major(version: string): number | undefined {
  const value = Number.parseInt(version.replace(/^[^0-9]*/, "").split(".")[0] ?? "", 10);
  return Number.isFinite(value) ? value : undefined;
}

export function planFrontendMigration(
  inventory: WorkspaceInventory,
  target: TargetProfile,
  currentVersions: Readonly<Record<string, string>> = {}
): FrontendMigrationPlan {
  if (!target.targetFramework.trim() || !target.targetVersion.trim() || !target.browserProfileRef.trim()) {
    throw new Error("target profile requires framework, version and browser profile");
  }
  if ((target.mode === "UX_REDESIGN" || target.mode === "CLIENT_REPLATFORM") && !target.approvedBy?.trim()) {
    return { strategy: target.mode, steps: [], blockers: ["HUMAN_PRODUCT_APPROVAL_REQUIRED"] };
  }

  const steps: MigrationStep[] = [
    step("baseline", "CAPTURE_UI_BASELINE", [], false, "WEB_LEGACY", ["BUILD", "ROUTE", "VISUAL", "ACCESSIBILITY"]),
    step("package-system", "MODERNIZE_PACKAGE_SYSTEM", ["baseline"], true, "WEB_LEGACY", ["LOCKFILE", "SUPPLY_CHAIN"]),
    step("runtime", "UPGRADE_RUNTIME", ["package-system"], true, "MODERN_WEB", ["BUILD", "TEST"]),
    step("design-tokens", "ESTABLISH_DESIGN_TOKENS", ["baseline"], false, "MODERN_WEB", ["DESIGN_OWNER_APPROVAL"]),
    step("compatibility", "ADD_COMPATIBILITY_LAYER", ["runtime", "design-tokens"], true, "MODERN_WEB", ["COMPATIBILITY_EXPIRY"])
  ];

  let frameworkTail = "compatibility";
  const blockers: string[] = [];
  if (inventory.frameworks.includes("ANGULARJS")) {
    steps.push(step("angularjs-hybrid", "ESTABLISH_ANGULARJS_HYBRID_BOUNDARY", [frameworkTail], false,
      "MODERN_WEB", ["SCOPE_BEHAVIOR", "DIGEST_BEHAVIOR", "EXIT_DATE"]));
    frameworkTail = "angularjs-hybrid";
  }
  if (inventory.frameworks.includes("ANGULAR")) {
    const from = major(currentVersions.ANGULAR ?? "");
    const to = major(target.targetVersion);
    if (from !== undefined && to !== undefined && to > from) {
      for (let value = from + 1; value <= to; value += 1) {
        const id = `angular-major-${value}`;
        steps.push(step(id, `ANGULAR_MAJOR_UPGRADE_${value}`, [frameworkTail], true, "MODERN_WEB", ["NG_UPDATE", "BUILD", "TEST"]));
        frameworkTail = id;
      }
    } else blockers.push("ANGULAR_VERSION_PATH_UNRESOLVED");
  }
  if (inventory.frameworks.includes("VUE2")) {
    for (const [id, type] of [
      ["vue-2-7", "UPGRADE_VUE_2_7"], ["vue-compat", "ENABLE_VUE_COMPAT"],
      ["vue-components", "MIGRATE_VUE_COMPONENTS"], ["vue-remove-compat", "REMOVE_VUE_COMPAT"]
    ] as const) {
      steps.push(step(id, type, [frameworkTail], id !== "vue-remove-compat", "MODERN_WEB",
        [id === "vue-remove-compat" ? "COMPAT_WARNINGS_ZERO_OR_APPROVED" : "BUILD", "VISUAL"]));
      frameworkTail = id;
    }
  }
  if (inventory.frameworks.includes("REACT")) {
    steps.push(step("react-classification", "CLASSIFY_REACT_CLASS_COMPONENTS", [frameworkTail], true,
      "MODERN_WEB", ["LIFECYCLE_GRAPH", "ERROR_BOUNDARY_POLICY"]));
    frameworkTail = "react-classification";
  }
  if (inventory.frameworks.includes("JQUERY")) {
    for (const version of ["1", "3", "4"] as const) {
      const id = `jquery-migrate-${version}`;
      steps.push(step(id, `JQUERY_MIGRATE_${version}`, [frameworkTail], true, "WEB_LEGACY", ["MIGRATE_WARNINGS_CAPTURED"]));
      frameworkTail = id;
    }
    steps.push(step("jquery-remove-migrate", "REMOVE_JQUERY_MIGRATE", [frameworkTail], false, "MODERN_WEB", ["MIGRATE_WARNINGS_ZERO"]));
    frameworkTail = "jquery-remove-migrate";
  }

  steps.push(
    step("route", "MIGRATE_ROUTE", [frameworkTail], true, "MODERN_WEB", ["ROUTE", "FORM", "AUTH", "API"]),
    step("visual", "VALIDATE_VISUAL", ["route"], false, "BROWSER_MATRIX", ["APPROVED_BASELINE", "STABLE_ENVIRONMENT"]),
    step("accessibility", "VALIDATE_ACCESSIBILITY", ["route"], false, "BROWSER_MATRIX", ["AUTOMATED", "KEYBOARD", "FOCUS", "MANUAL_PROFILE"]),
    step("performance", "VALIDATE_PERFORMANCE", ["route"], false, "BROWSER_MATRIX", ["BUNDLE_BUDGET", "CLIENT_SECURITY"]),
    step("canary", "RELEASE_CANARY", ["visual", "accessibility", "performance"], false, "RELEASE_PROVIDER", ["HUMAN_RELEASE_APPROVAL"]),
    step("remove-compatibility", "REMOVE_COMPATIBILITY_LAYER", ["canary"], false, "MODERN_WEB", ["LEGACY_USAGE_ZERO", "OWNER_APPROVAL"])
  );
  return { strategy: target.mode, steps, blockers };
}
