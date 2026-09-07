import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { posix, resolve } from "node:path";
import test from "node:test";

import {
  MINIAPP_CANONICAL_SCHEMA_FILES,
  MINIAPP_DECLARED_OUTPUT_CATALOG,
  MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS,
  materializeMiniappCombinedOutputIndex,
  materializeMiniappDeclaredOutputs,
  materializeMiniappDeclaredOutputIndex,
  materializeMiniappGeneratedProjectArtifacts,
  materializeMiniappGeneratedProjectBasePath,
  materializeMiniappOutputPath,
  miniappDeclaredOutputSchema,
  validateMiniappDeclaredOutputCatalog,
  type MiniappDeclaredOutputArtifact,
  type MiniappDeclaredOutputState,
} from "../src/miniapp-output-contracts.js";
import {
  MINIAPP_SKILL_CATALOG,
  runMiniappConversion,
  type MiniappConversionRun,
} from "../src/miniapp-skill-runtime.js";
import { conversionInput, vueTodoFiles } from "./miniapp-test-fixture.js";

const OUTPUT_STATES = new Set<MiniappDeclaredOutputState>([
  "PASSED_LOCAL",
  "BLOCKED",
  "NOT_RUN",
  "NOT_APPLICABLE",
]);

function artifactKey(
  artifact: Pick<MiniappDeclaredOutputArtifact, "ownerSkill" | "declaredPattern">,
): string {
  return `${artifact.ownerSkill}\u0000${artifact.declaredPattern}`;
}

function decodedContent(artifact: MiniappDeclaredOutputArtifact): unknown {
  return JSON.parse(artifact.content) as unknown;
}

function decodedObject(
  artifact: MiniappDeclaredOutputArtifact,
): Readonly<Record<string, unknown>> {
  const decoded = decodedContent(artifact);
  assert.ok(decoded !== null && typeof decoded === "object" && !Array.isArray(decoded));
  return decoded as Readonly<Record<string, unknown>>;
}

function selectOwner(
  artifacts: readonly MiniappDeclaredOutputArtifact[],
  ownerSkill: string,
): readonly MiniappDeclaredOutputArtifact[] {
  return artifacts.filter((artifact) => artifact.ownerSkill === ownerSkill);
}

test("declared-output catalog exactly transcribes all 22 Skills, 40 tasks and 88 outputs", () => {
  assert.deepEqual(validateMiniappDeclaredOutputCatalog(), {
    requiredOutputs: 88,
    skills: 22,
    tasks: 40,
  });
  assert.deepEqual(
    MINIAPP_DECLARED_OUTPUT_CATALOG.map((contract) => contract.ownerSkill),
    MINIAPP_SKILL_CATALOG.map((skill) => skill.name),
  );

  const tasks = MINIAPP_DECLARED_OUTPUT_CATALOG.flatMap((contract) => contract.taskIds);
  assert.deepEqual(
    [...tasks].sort(),
    Array.from(
      { length: 40 },
      (_value, index) => `MAPP-${String(index + 1).padStart(3, "0")}`,
    ),
  );
  assert.equal(new Set(tasks).size, 40);
  assert.equal(
    MINIAPP_DECLARED_OUTPUT_CATALOG.reduce(
      (count, contract) => count + contract.requiredOutputs.length,
      0,
    ),
    88,
  );
  assert.ok(
    MINIAPP_DECLARED_OUTPUT_CATALOG.every(
      (contract) =>
        contract.requiredOutputs.length > 0 &&
        new Set(contract.requiredOutputs).size === contract.requiredOutputs.length,
    ),
  );
  const canonicalContractIdentity = MINIAPP_DECLARED_OUTPUT_CATALOG.map(
    (contract) =>
      `${contract.ownerSkill}|${contract.taskIds.join(",")}|${contract.requiredOutputs.join("\u001f")}`,
  ).join("\n");
  assert.equal(
    createHash("sha256").update(canonicalContractIdentity, "utf8").digest("hex"),
    "d525998f903c81e793e5c0d6053b5404841211f35cf9167b4dce7e71763ea3c0",
  );
  assert.equal(MINIAPP_CANONICAL_SCHEMA_FILES.length, 14);
  assert.equal(new Set(MINIAPP_CANONICAL_SCHEMA_FILES).size, 14);
  assert.equal(MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS.length, 12);
  for (const binding of MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS) {
    const contract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(
      (candidate) => candidate.ownerSkill === binding.ownerSkill,
    );
    assert.ok(contract);
    assert.ok((contract.requiredOutputs as readonly string[]).includes(binding.declaredPattern));
    assert.ok(MINIAPP_CANONICAL_SCHEMA_FILES.includes(binding.schema));
  }
});

test("every declaration materializes once with deterministic safe path, bytes and digest", () => {
  const run = runMiniappConversion(conversionInput());
  const first = materializeMiniappDeclaredOutputs(run);
  const second = materializeMiniappDeclaredOutputs(run);
  assert.deepEqual(first, second);
  assert.equal(first.length, 88);

  const expectedKeys = new Set(
    MINIAPP_DECLARED_OUTPUT_CATALOG.flatMap((contract) =>
      contract.requiredOutputs.map((declaredPattern) =>
        artifactKey({ declaredPattern, ownerSkill: contract.ownerSkill }),
      ),
    ),
  );
  assert.deepEqual(new Set(first.map(artifactKey)), expectedKeys);
  assert.equal(new Set(first.map((artifact) => artifact.materializedPath)).size, 88);

  for (const artifact of first) {
    assert.ok(OUTPUT_STATES.has(artifact.state));
    assert.ok(artifact.content.length > 0);
    assert.equal(artifact.bytes, Buffer.byteLength(artifact.content, "utf8"));
    assert.equal(
      artifact.digest,
      `sha256:${createHash("sha256").update(artifact.content, "utf8").digest("hex")}`,
    );
    assert.match(artifact.digest, /^sha256:[a-f0-9]{64}$/u);
    assert.equal(posix.isAbsolute(artifact.materializedPath), false);
    assert.equal(posix.normalize(artifact.materializedPath), artifact.materializedPath);
    assert.ok(artifact.materializedPath.startsWith(`runs/${run.runId}/`));
    assert.equal(artifact.materializedPath.includes("\\"), false);
    assert.equal(
      artifact.materializedPath
        .split("/")
        .some((segment) => segment === "" || segment === "." || segment === ".."),
      false,
    );
    if (artifact.declaredPattern.endsWith(".md")) {
      assert.match(artifact.content, /^# /u);
    } else {
      assert.notEqual(decodedContent(artifact), undefined);
    }
  }
});

test("codegen wildcards index exact locally closed project files while blocked flows stay placeholders", () => {
  const run = runMiniappConversion(conversionInput());
  const artifacts = materializeMiniappDeclaredOutputs(run);
  const candidateArtifacts = materializeMiniappGeneratedProjectArtifacts(run);
  assert.deepEqual(candidateArtifacts, materializeMiniappGeneratedProjectArtifacts(run));
  assert.deepEqual(
    [...new Set(candidateArtifacts.map((artifact) => artifact.platform))],
    ["wechat", "alipay"],
  );
  assert.equal(
    candidateArtifacts.length,
    run.generatedProjects
      .filter(
        (project) =>
          project.status === "GENERATED" && project.staticValidation === "PASSED",
      )
      .reduce((count, project) => count + Object.keys(project.files).length, 0),
  );
  assert.equal(
    new Set([
      ...artifacts.map((artifact) => artifact.materializedPath.toLowerCase()),
      ...candidateArtifacts.map((artifact) => artifact.materializedPath.toLowerCase()),
    ]).size,
    artifacts.length + candidateArtifacts.length,
  );
  for (const candidate of candidateArtifacts) {
    const project = run.generatedProjects.find(
      (item) => item.platform === candidate.platform,
    );
    assert.ok(project);
    assert.equal(candidate.state, "PASSED_LOCAL");
    assert.equal(candidate.content, project.files[candidate.sourcePath]);
    assert.equal(candidate.bytes, Buffer.byteLength(candidate.content, "utf8"));
    assert.equal(
      candidate.digest,
      `sha256:${createHash("sha256").update(candidate.content, "utf8").digest("hex")}`,
    );
    assert.equal(
      candidate.declaredBasePath,
      materializeMiniappGeneratedProjectBasePath(run, candidate.platform),
    );
    assert.equal(
      candidate.declaredBasePath,
      `runs/${run.runId}/platforms/${candidate.platform}`,
    );
    assert.equal(
      candidate.materializedPath,
      `${candidate.declaredBasePath}/${candidate.sourcePath}`,
    );
    assert.ok(candidate.materializedPath.startsWith(`runs/${run.runId}/`));
    assert.equal(posix.normalize(candidate.materializedPath), candidate.materializedPath);
  }

  const wildcardArtifacts = artifacts.filter((artifact) =>
    artifact.declaredPattern.endsWith("/**"),
  );
  assert.equal(wildcardArtifacts.length, 7);
  for (const artifact of wildcardArtifacts) {
    if (artifact.declaredPattern.startsWith("platforms/")) {
      const platform = artifact.declaredPattern.split("/")[1];
      assert.ok(
        platform === "wechat" ||
          platform === "alipay" ||
          platform === "douyin" ||
          platform === "xiaohongshu",
      );
      const project = run.generatedProjects.find(
        (candidate) => candidate.platform === platform,
      );
      assert.ok(project);
      if (project.status === "GENERATED" && project.staticValidation === "PASSED") {
        assert.equal(artifact.state, "PASSED_LOCAL");
        assert.ok(artifact.materializedPath.endsWith("/project-index.json"));
        const body = decodedObject(artifact);
        assert.equal(body.exact_declared_files_materialized, true);
        assert.equal(
          body.declared_base_path,
          materializeMiniappGeneratedProjectBasePath(run, platform),
        );
        assert.deepEqual(
          body.files,
          candidateArtifacts
            .filter((candidate) => candidate.platform === platform)
            .map((candidate) => ({
              bytes: candidate.bytes,
              path: candidate.materializedPath,
              sha256: candidate.digest.slice("sha256:".length),
              source_path: candidate.sourcePath,
            })),
        );
      } else {
        assert.equal(artifact.state, "BLOCKED");
        assert.ok(artifact.materializedPath.endsWith("/blocked-surrogate-index.json"));
        const body = decodedObject(artifact);
        assert.equal(body.exact_declared_files_materialized, false);
        assert.deepEqual(body.files, []);
      }
    } else {
      assert.equal(artifact.state, "NOT_RUN");
      assert.ok(artifact.materializedPath.endsWith("/not-run-placeholder-index.json"));
    }
  }

  for (const platform of [
    "wechat",
    "alipay",
    "douyin",
    "xiaohongshu",
  ] as const) {
    const owner = `${platform}-miniapp-codegen` as const;
    const basePath = `runs/${run.runId}/platforms/${platform}/`;
    const owned = selectOwner(artifacts, owner);
    assert.equal(owned.length, 3);
    assert.ok(
      owned.every((artifact) => artifact.materializedPath.startsWith(basePath)),
      `${owner} outputs must remain inside the exact target platform directory`,
    );
  }

  const htmlArtifacts = artifacts.filter((artifact) =>
    artifact.declaredPattern.endsWith(".html"),
  );
  assert.equal(htmlArtifacts.length, 3);
  assert.ok(htmlArtifacts.every((artifact) => artifact.state === "NOT_RUN"));
  assert.ok(
    htmlArtifacts.every((artifact) =>
      artifact.materializedPath.endsWith(`${artifact.declaredPattern}.not-run.json`),
    ),
  );

  const markdownArtifacts = artifacts.filter((artifact) =>
    artifact.declaredPattern.endsWith(".md"),
  );
  assert.equal(markdownArtifacts.length, 3);
  assert.ok(
    markdownArtifacts.every(
      (artifact) => artifact.state === "PASSED_LOCAL" || artifact.state === "BLOCKED",
    ),
  );
  for (const artifact of markdownArtifacts) {
    assert.ok(artifact.materializedPath.endsWith(`/${artifact.declaredPattern}`));
    assert.match(artifact.content, /^# /u);
    assert.throws(() => JSON.parse(artifact.content), /Unexpected|JSON/u);
  }

  const combinedPlaceholder = artifacts.find(
    (artifact) => artifact.declaredPattern === "最终 migration-evidence.json 与兼容性报告",
  );
  assert.equal(combinedPlaceholder?.state, "BLOCKED");
  assert.ok(combinedPlaceholder?.materializedPath.endsWith(".blocked.json"));
});

test("Schema-bound bodies are exact payloads and provenance lives in independent indexes", () => {
  const run = runMiniappConversion(conversionInput());
  const artifacts = materializeMiniappDeclaredOutputs(run);
  const generatedArtifacts = materializeMiniappGeneratedProjectArtifacts(run);
  const indexArtifacts = artifacts.filter(
    (artifact) =>
      artifact.declaredPattern === "runs/<run-id>/artifacts-index.json" ||
      artifact.declaredPattern === "artifact-index.json",
  );
  const bodyArtifacts = artifacts.filter(
    (artifact) => !indexArtifacts.includes(artifact),
  );
  const declaredOnlyIndex = materializeMiniappDeclaredOutputIndex(bodyArtifacts);
  const expectedIndex = materializeMiniappCombinedOutputIndex(run);
  assert.equal(indexArtifacts.length, 2);
  assert.equal(declaredOnlyIndex.length, 86);
  assert.equal(expectedIndex.length, 86 + generatedArtifacts.length);

  for (const artifact of indexArtifacts) {
    const body = decodedObject(artifact);
    assert.equal(body.schema_version, "1.0.0");
    assert.equal(body.run_id, run.runId);
    assert.deepEqual(body.artifacts, expectedIndex);
    assert.deepEqual(
      body.self_referential_outputs_excluded,
      indexArtifacts.map((candidate) => candidate.materializedPath),
    );
  }

  for (const entry of expectedIndex) {
    const artifact = [...bodyArtifacts, ...generatedArtifacts].find(
      (candidate) => candidate.materializedPath === entry.materialized_path,
    );
    assert.ok(artifact);
    assert.equal(entry.owner_skill, artifact.ownerSkill);
    assert.equal(entry.state, artifact.state);
    assert.equal(entry.digest, artifact.digest);
    assert.equal(entry.bytes, artifact.bytes);
    if ("sourcePath" in artifact) {
      assert.equal(entry.schema, null);
      assert.match(entry.artifact_id, /^generated-member-[a-f0-9]{24}$/u);
    } else {
      assert.equal(
        entry.schema,
        miniappDeclaredOutputSchema(artifact.ownerSkill, artifact.declaredPattern) ===
          undefined
          ? null
          : `schemas/${miniappDeclaredOutputSchema(
              artifact.ownerSkill,
              artifact.declaredPattern,
            )}`,
      );
      assert.match(entry.artifact_id, /^declared-output-[a-f0-9]{24}$/u);
    }
  }

  for (const binding of MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS) {
    const artifact = artifacts.find(
      (candidate) =>
        candidate.ownerSkill === binding.ownerSkill &&
        candidate.declaredPattern === binding.declaredPattern,
    );
    assert.ok(artifact);
    const body = decodedObject(artifact);
    for (const wrapperKey of [
      "ownerSkill",
      "declaredPattern",
      "state",
      "digest",
      "payload",
      "runId",
      "schemaVersion",
      "certification",
    ]) {
      assert.equal(Object.hasOwn(body, wrapperKey), false);
    }
    assert.ok(
      Object.keys(body).every((key) => /^[a-z][a-z0-9_]*$/u.test(key)),
      `${binding.declaredPattern} must expose snake_case root fields`,
    );
  }

  const migrationEvidence = artifacts.find(
    (artifact) =>
      artifact.ownerSkill === "miniapp-migration-evidence-reporter" &&
      artifact.declaredPattern === "migration-evidence.json",
  );
  assert.ok(migrationEvidence);
  assert.equal(migrationEvidence.state, "BLOCKED");
  const migrationBody = decodedObject(migrationEvidence);
  const evidenceArtifacts = migrationBody.artifacts as readonly Readonly<Record<string, unknown>>[];
  assert.ok(evidenceArtifacts.length > 0);
  const evidenceIds = new Set(evidenceArtifacts.map((artifact) => artifact.artifact_id));
  assert.ok(evidenceIds.has("request"));
  assert.ok(evidenceIds.has("conversion-plan"));
  for (const claim of migrationBody.claims as readonly Readonly<
    Record<string, unknown>
  >[]) {
    assert.ok((claim.evidence_refs as readonly string[]).every((reference) => evidenceIds.has(reference)));
  }
  for (const gate of migrationBody.gates as readonly Readonly<
    Record<string, unknown>
  >[]) {
    assert.ok((gate.evidence_refs as readonly string[]).every((reference) => evidenceIds.has(reference)));
    if (gate.status === "passed") assert.ok((gate.evidence_refs as readonly string[]).length > 0);
  }
});

test("all 14 canonical Draft 2020-12 Schemas and every bound body validate for real", () => {
  const packageRootCandidates = [
    resolve(process.cwd(), "../../skills/elmos-frontend-to-miniapp-skills-v1.0.0"),
    resolve(process.cwd(), "skills/elmos-frontend-to-miniapp-skills-v1.0.0"),
  ];
  const packageRoot = packageRootCandidates.find((candidate) =>
    existsSync(resolve(candidate, "schemas/project-inventory.schema.json")),
  );
  assert.ok(packageRoot, "canonical frontend-to-miniapp package root must be available");

  const artifacts = materializeMiniappDeclaredOutputs(
    runMiniappConversion(conversionInput()),
  );
  const cases = MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS.map((binding) => {
    const artifact = artifacts.find(
      (candidate) =>
        candidate.ownerSkill === binding.ownerSkill &&
        candidate.declaredPattern === binding.declaredPattern,
    );
    assert.ok(artifact);
    return {
      instance: decodedContent(artifact),
      output: `${binding.ownerSkill}:${binding.declaredPattern}`,
      schema: binding.schema,
    };
  });
  const validatorScript = String.raw`
import copy
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

payload = json.load(sys.stdin)
root = pathlib.Path(payload["package_root"])
schema_root = root / "schemas"
fixture_root = root / "fixtures"
for schema_name in payload["schema_files"]:
    schema = json.loads((schema_root / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    fixture_name = schema_name.replace(".schema.json", ".valid.json")
    fixture = json.loads((fixture_root / fixture_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)
for case in payload["cases"]:
    schema = json.loads((schema_root / case["schema"]).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(case["instance"])
    required = schema.get("required", [])
    if required and isinstance(case["instance"], dict):
        invalid = copy.deepcopy(case["instance"])
        invalid.pop(required[0], None)
        if validator.is_valid(invalid):
            raise AssertionError(
                f'{case["output"]}: validator accepted body without {required[0]}'
            )
print(json.dumps({"schemas": len(payload["schema_files"]), "cases": len(payload["cases"])}))
`;
  const validation = spawnSync(
    process.env.ELMOS_MINIAPP_SCHEMA_PYTHON ?? "python3.11",
    ["-c", validatorScript],
    {
      encoding: "utf8",
      input: JSON.stringify({
        cases,
        package_root: packageRoot,
        schema_files: MINIAPP_CANONICAL_SCHEMA_FILES,
      }),
      maxBuffer: 16 * 1024 * 1024,
    },
  );
  assert.equal(validation.status, 0, validation.stderr);
  assert.deepEqual(JSON.parse(validation.stdout), {
    cases: 12,
    schemas: 14,
  });
});

test("semantic-ir Schema body closes binary inventory assets by exact content digest", () => {
  const assetBytes = new Uint8Array([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0xff,
  ]);
  const payloadBytes = new Uint8Array([0x00, 0xff, 0x10, 0x80, 0x01]);
  const files = [
    ...vueTodoFiles,
    {
      content: assetBytes,
      path: "src/assets/logo.png",
    },
    {
      content: payloadBytes,
      path: "payload.bin",
    },
  ] as const;
  const run = runMiniappConversion(conversionInput(files, "vue3", ["wechat"]));
  assert.deepEqual(run.inventory.assets, ["payload.bin", "src/assets/logo.png"]);
  const semanticArtifact = materializeMiniappDeclaredOutputs(run).find(
    (artifact) =>
      artifact.ownerSkill === "miniapp-semantic-ir" &&
      artifact.declaredPattern === "semantic-ir.json",
  );
  assert.ok(semanticArtifact);
  const body = decodedObject(semanticArtifact);
  const application = body.application as Readonly<Record<string, unknown>>;
  const assets = application.assets as readonly Readonly<Record<string, unknown>>[];
  assert.equal(assets.length, 2);
  assert.deepEqual(assets.map((asset) => asset.name), [
    "payload.bin",
    "src/assets/logo.png",
  ]);
  const logo = assets.find((asset) => asset.name === "src/assets/logo.png");
  const payload = assets.find((asset) => asset.name === "payload.bin");
  assert.ok(logo);
  assert.ok(payload);
  assert.equal(
    logo.content_hash,
    createHash("sha256").update(assetBytes).digest("hex"),
  );
  assert.deepEqual(logo.children, []);
  assert.deepEqual(logo.references, []);
  assert.deepEqual(logo.props, {
    byte_count: assetBytes.byteLength,
    file_kind: "binary",
    path: "src/assets/logo.png",
    status: "binary",
  });
  assert.equal(
    payload.content_hash,
    createHash("sha256").update(payloadBytes).digest("hex"),
  );
  assert.deepEqual(payload.props, {
    byte_count: payloadBytes.byteLength,
    file_kind: "binary",
    path: "payload.bin",
    status: "binary",
  });

  const packageRootCandidates = [
    resolve(process.cwd(), "../../skills/elmos-frontend-to-miniapp-skills-v1.0.0"),
    resolve(process.cwd(), "skills/elmos-frontend-to-miniapp-skills-v1.0.0"),
  ];
  const packageRoot = packageRootCandidates.find((candidate) =>
    existsSync(resolve(candidate, "schemas/semantic-ir.schema.json")),
  );
  assert.ok(packageRoot);
  const validation = spawnSync(
    process.env.ELMOS_MINIAPP_SCHEMA_PYTHON ?? "python3.11",
    [
      "-c",
      String.raw`
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker
payload = json.load(sys.stdin)
schema = json.loads(pathlib.Path(payload["schema"]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload["instance"])
`,
    ],
    {
      encoding: "utf8",
      input: JSON.stringify({
        instance: body,
        schema: resolve(packageRoot, "schemas/semantic-ir.schema.json"),
      }),
      maxBuffer: 16 * 1024 * 1024,
    },
  );
  assert.equal(validation.status, 0, validation.stderr);

  const missingAssetRun = {
    ...run,
    inventory: {
      ...run.inventory,
      files: run.inventory.files.filter((file) => file.path !== "src/assets/logo.png"),
    },
  } as MiniappConversionRun;
  const missingAssetArtifact = materializeMiniappDeclaredOutputs(missingAssetRun).find(
    (artifact) =>
      artifact.ownerSkill === "miniapp-semantic-ir" &&
      artifact.declaredPattern === "semantic-ir.json",
  );
  assert.equal(missingAssetArtifact?.state, "BLOCKED");
  const missingBody = decodedObject(missingAssetArtifact!);
  const missingApplication = missingBody.application as Readonly<Record<string, unknown>>;
  const missingAssets = missingApplication.assets as readonly Readonly<
    Record<string, unknown>
  >[];
  const missingLogo = missingAssets.find(
    (asset) => asset.name === "src/assets/logo.png",
  );
  assert.ok(missingLogo);
  assert.equal(
    (missingLogo.props as Readonly<Record<string, unknown>>).status,
    "inventory-file-missing",
  );
});

test("official build, differential, visual, CI and release evidence stays explicitly NOT_RUN", () => {
  const run = runMiniappConversion(conversionInput());
  const artifacts = materializeMiniappDeclaredOutputs(run);

  for (const owner of [
    "miniapp-differential-testing",
    "miniapp-visual-regression-testing",
    "miniapp-ci-build-release",
  ] as const) {
    const owned = selectOwner(artifacts, owner);
    assert.ok(owned.length > 0);
    assert.ok(owned.every((artifact) => artifact.state === "NOT_RUN"));
    assert.ok(owned.every((artifact) => artifact.content.includes("NOT_RUN")));
  }

  for (const owner of [
    "wechat-miniapp-codegen",
    "alipay-miniapp-codegen",
    "douyin-miniapp-codegen",
    "xiaohongshu-miniapp-codegen",
  ] as const) {
    const report = selectOwner(artifacts, owner).find((artifact) =>
      artifact.declaredPattern.endsWith("-codegen-report.json"),
    );
    assert.ok(report);
    const project = run.generatedProjects.find(
      (candidate) => `${candidate.platform}-miniapp-codegen` === owner,
    );
    assert.ok(project);
    assert.equal(
      report.state,
      project.status === "GENERATED" && project.staticValidation === "PASSED"
        ? "PASSED_LOCAL"
        : "BLOCKED",
    );
    assert.ok(report.content.includes('"officialBuild":"NOT_RUN"'));
    assert.ok(report.content.includes('"certification":"NOT_CERTIFIED"'));
  }

  const patches = artifacts.find(
    (artifact) =>
      artifact.ownerSkill === "miniapp-auto-repair-loop" &&
      artifact.declaredPattern === "patches/**",
  );
  const postRepair = artifacts.find(
    (artifact) =>
      artifact.ownerSkill === "miniapp-auto-repair-loop" &&
      artifact.declaredPattern === "post-repair-validation.json",
  );
  assert.equal(patches?.state, "NOT_RUN");
  assert.equal(postRepair?.state, "NOT_RUN");
  assert.ok(
    selectOwner(artifacts, "miniapp-auto-repair-loop").every(
      (artifact) => artifact.state === "NOT_RUN",
    ),
  );
  for (const declaredPattern of ["license-report.json", "supply-chain-findings.json"]) {
    assert.equal(
      artifacts.find(
        (artifact) =>
          artifact.ownerSkill === "miniapp-third-party-dependency-migrator" &&
          artifact.declaredPattern === declaredPattern,
      )?.state,
      "NOT_RUN",
    );
  }
});

test("source analyzers and unrequested targets materialize explicit NOT_APPLICABLE records", () => {
  const run = runMiniappConversion(conversionInput(undefined, "vue3", ["wechat"]));
  const artifacts = materializeMiniappDeclaredOutputs(run);

  assert.ok(
    selectOwner(artifacts, "vue-to-miniapp-analyzer").every(
      (artifact) => artifact.state !== "NOT_APPLICABLE",
    ),
  );
  assert.ok(
    selectOwner(artifacts, "react-to-miniapp-analyzer").every(
      (artifact) => artifact.state === "NOT_APPLICABLE",
    ),
  );
  assert.ok(
    selectOwner(artifacts, "flutter-widget-semantic-reconstructor").every(
      (artifact) => artifact.state === "NOT_APPLICABLE",
    ),
  );
  assert.ok(
    selectOwner(artifacts, "wechat-miniapp-codegen").every(
      (artifact) => artifact.state !== "NOT_APPLICABLE",
    ),
  );
  for (const owner of [
    "alipay-miniapp-codegen",
    "douyin-miniapp-codegen",
    "xiaohongshu-miniapp-codegen",
  ] as const) {
    const owned = selectOwner(artifacts, owner);
    assert.ok(owned.every((artifact) => artifact.state === "NOT_APPLICABLE"));
    assert.ok(owned.every((artifact) => artifact.content.includes("not requested")));
    const wildcard = owned.find((artifact) => artifact.declaredPattern.endsWith("/**"));
    assert.ok(wildcard?.materializedPath.endsWith("/not-applicable-placeholder-index.json"));
  }
});

test("generated project materialization rejects escaped, colliding and identity-drifted files", () => {
  const run = runMiniappConversion(conversionInput(undefined, undefined, ["wechat"]));
  const project = run.generatedProjects[0]!;
  const firstArtifact = project.artifacts[0]!;

  for (const sourcePath of [
    "../escape.js",
    "/absolute.js",
    "pages\\escape.js",
    "pages/%2e%2e/escape.js",
    "pages/CON.json",
    "pages/file.",
    "project-index.json",
    "Project-Index.json/nested.js",
  ]) {
    assert.throws(
      () =>
        materializeMiniappGeneratedProjectArtifacts({
          ...run,
          generatedProjects: [
            {
              ...project,
              files: { [sourcePath]: firstArtifact.path in project.files
                ? project.files[firstArtifact.path]!
                : "safe" },
              artifacts: [{
                ...firstArtifact,
                path: sourcePath,
                sha256: `sha256:${createHash("sha256")
                  .update(
                    firstArtifact.path in project.files
                      ? project.files[firstArtifact.path]!
                      : "safe",
                    "utf8",
                  )
                  .digest("hex")}`,
                bytes: Buffer.byteLength(
                  firstArtifact.path in project.files
                    ? project.files[firstArtifact.path]!
                    : "safe",
                  "utf8",
                ),
              }],
            },
          ],
        } as MiniappConversionRun),
      /unsafe generated miniapp project path/u,
    );
  }

  const collisionFiles = {
    "App.js": "first",
    "app.js": "second",
  };
  assert.throws(
    () =>
      materializeMiniappGeneratedProjectArtifacts({
        ...run,
        generatedProjects: [{
          ...project,
          files: collisionFiles,
          artifacts: Object.entries(collisionFiles).map(([path, content]) => ({
            ...firstArtifact,
            path,
            bytes: Buffer.byteLength(content, "utf8"),
            sha256: `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`,
          })),
        }],
      } as MiniappConversionRun),
    /case-insensitive generated miniapp project path collision/u,
  );

  const prefixCollisionFiles = {
    "pages/home": "file",
    "pages/home/index.js": "nested",
  };
  assert.throws(
    () =>
      materializeMiniappGeneratedProjectArtifacts({
        ...run,
        generatedProjects: [{
          ...project,
          files: prefixCollisionFiles,
          artifacts: Object.entries(prefixCollisionFiles).map(([path, content]) => ({
            ...firstArtifact,
            path,
            bytes: Buffer.byteLength(content, "utf8"),
            sha256: `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`,
          })),
        }],
      } as MiniappConversionRun),
    /file\/directory collision/u,
  );

  assert.throws(
    () =>
      materializeMiniappGeneratedProjectArtifacts({
        ...run,
        generatedProjects: [{
          ...project,
          artifacts: project.artifacts.map((artifact, index) =>
            index === 0 ? { ...artifact, bytes: artifact.bytes + 1 } : artifact,
          ),
        }],
      } as MiniappConversionRun),
    /artifact identity mismatch/u,
  );
});

test("path token substitution rejects traversal, ambiguity and unknown tokens", () => {
  const valid = {
    "run-id": "miniapp-run-conv-fixture-0123456789abcdef",
    framework: "uni-app",
    target: "wechat",
  } as const;
  assert.equal(
    materializeMiniappOutputPath(
      "runs/<run-id>/declared-outputs/<framework>/<target>/artifact.json",
      valid,
    ),
    "runs/miniapp-run-conv-fixture-0123456789abcdef/declared-outputs/uni-app/wechat/artifact.json",
  );

  for (const unsafe of [
    "../escape",
    "safe/../../escape",
    "safe\\escape",
    "%2e%2e",
    "double..dot",
    "not normalized",
  ]) {
    assert.throws(
      () =>
        materializeMiniappOutputPath("runs/<run-id>/<target>/<framework>/artifact.json", {
          ...valid,
          "run-id": unsafe,
        }),
      /unsafe/u,
    );
  }
  assert.throws(
    () => materializeMiniappOutputPath("runs/<unknown>/artifact.json", valid),
    /unknown/u,
  );
  assert.throws(
    () => materializeMiniappOutputPath("runs/<UNKNOWN>/artifact.json", valid),
    /unsafe/u,
  );
  const indexedArtifact = materializeMiniappDeclaredOutputs(
    runMiniappConversion(conversionInput()),
  ).find((artifact) => artifact.declaredPattern === "state-lowering-plan.json");
  assert.ok(indexedArtifact);
  assert.throws(
    () => materializeMiniappDeclaredOutputIndex([{
      ...indexedArtifact,
      materializedPath: "../escape.json",
    }]),
    /unsafe indexed miniapp output path/u,
  );
  assert.throws(
    () => materializeMiniappDeclaredOutputIndex([
      indexedArtifact,
      {
        ...indexedArtifact,
        materializedPath: indexedArtifact.materializedPath.toUpperCase(),
      },
    ]),
    /duplicate path/u,
  );
  assert.throws(
    () => materializeMiniappDeclaredOutputIndex([{
      ...indexedArtifact,
      state: "CERTIFIED" as never,
    }]),
    /invalid miniapp declared output state/u,
  );
  assert.throws(
    () => materializeMiniappOutputPath("runs/%2e%2e/artifact.json", valid),
    /unsafe/u,
  );
  assert.throws(
    () => materializeMiniappOutputPath("runs/CON/artifact.json", valid),
    /unsafe/u,
  );
  assert.throws(
    () => materializeMiniappOutputPath("runs/trailing./artifact.json", valid),
    /unsafe/u,
  );
  assert.throws(
    () =>
      materializeMiniappDeclaredOutputs({
        ...runMiniappConversion(conversionInput()),
        runId: "../escape",
      } as MiniappConversionRun),
    /unsafe/u,
  );
});
