import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { runMiniappConversion } from "../src/miniapp-skill-runtime.js";
import { miniappPlatformDescriptor } from "../src/miniapp-planning.js";
import { generateMiniappTarget } from "../src/miniapp-target-generation.js";
import { miniappIrDigest } from "../src/miniapp-semantic-ir.js";
import { conversionInput, vueTodoFiles } from "./miniapp-test-fixture.js";

test("one semantic IR generates four distinct native miniapp project structures", () => {
  const run = runMiniappConversion(conversionInput());
  assert.deepEqual(run.generatedProjects.map(project => project.platform), ["wechat", "alipay", "douyin", "xiaohongshu"]);
  assert.deepEqual(Object.fromEntries(run.generatedProjects.map(project => [project.platform, project.status])), {
    wechat: "GENERATED",
    alipay: "GENERATED",
    douyin: "GENERATED_WITH_BLOCKERS",
    xiaohongshu: "GENERATED_WITH_BLOCKERS",
  });
  for (const project of run.generatedProjects) {
    const descriptor = miniappPlatformDescriptor(project.platform);
    assert.equal(project.staticValidation, "PASSED");
    assert.equal(project.officialBuild, "NOT_RUN");
    assert.equal(project.deviceRuntime, "NOT_RUN");
    assert.equal(project.certification, "NOT_CERTIFIED");
    assert.ok(Object.keys(project.files).some(path => path.endsWith(descriptor.templateExtension)));
    assert.ok(Object.keys(project.files).some(path => path.endsWith(descriptor.styleExtension)));
    assert.ok(Object.hasOwn(project.files, descriptor.projectFile));
    assert.ok(Object.hasOwn(project.files, "adapters/platform.js"));
    assert.doesNotMatch(Object.values(project.files).join("\n"), /<web-view\b|BEGIN (?:RSA |EC )?PRIVATE KEY/);
    const serializedTrace = JSON.parse(project.files["trace-map.json"]!) as Record<string, string[]>;
    for (const artifact of project.artifacts) {
      const content = project.files[artifact.path]!;
      assert.equal(artifact.sha256, `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`);
      assert.equal(artifact.bytes, Buffer.byteLength(content, "utf8"));
      if (artifact.path !== "trace-map.json") assert.deepEqual(serializedTrace[artifact.path], artifact.sourceNodeIds);
      if (artifact.role === "evidence") assert.deepEqual(artifact.sourceNodeIds, [], `${project.platform}:${artifact.path} must not self-credit trace coverage`);
    }
    assert.ok(project.artifacts.some(artifact => artifact.role === "runtime" && artifact.sourceNodeIds.length > 0));
  }
  assert.notEqual(run.generatedProjects[0]!.deterministicDigest, run.generatedProjects[1]!.deterministicDigest);
  assert.throws(() => generateMiniappTarget("wechat", run.semanticIr, {
    ...run.plan,
    summary: { ...run.plan.summary, A: run.plan.summary.A + 1 },
  }, run.request, run.inventory), /plan deterministic digest does not match its content/u);
  assert.throws(() => generateMiniappTarget("wechat", run.semanticIr, run.plan, {
    ...run.request,
    policy: { ...run.request.policy, priority: "maintainability" },
  }, run.inventory), /exact request and IR/u);
  const { deterministicDigest: _ignored, ...forgedBody } = {
    ...run.plan,
    findings: [],
  };
  void _ignored;
  const forgedPlan = { ...forgedBody, deterministicDigest: miniappIrDigest(forgedBody) };
  assert.throws(
    () => generateMiniappTarget("wechat", run.semanticIr, forgedPlan, run.request, run.inventory),
    /canonical semantic reconstruction/u,
  );
});

test("generated four-platform Todo candidates preserve trim, blank guard, append order, clear and application scope", () => {
  const run = runMiniappConversion(conversionInput());
  const loopPrefix = { wechat: "wx:for", alipay: "a:for", douyin: "tt:for", xiaohongshu: "xhs:for" } as const;
  for (const project of run.generatedProjects) {
    const template = Object.entries(project.files).find(([path]) => /\.(?:wxml|axml|ttml|xhsml)$/u.test(path))?.[1] ?? "";
    assert.match(template, /Todos/u);
    assert.match(template, />Add<\/button>/u);
    assert.match(template, /aria-label="Todo text"/u);
    assert.match(template, /required="true"/u);
    assert.match(template, /disabled="\{\{!canSubmit0\}\}"/u);
    assert.match(template, new RegExp(`${loopPrefix[project.platform]}=`, "u"));
    assert.match(template, /\{\{item\.value\}\}/u);
    assert.match(template, /(?:wx:key|a:key|tt:key|xhs:key)="__elmosKey"/u);

    let application: { globalData: Record<string, unknown> } | undefined;
    runInNewContext(project.files["app.js"]!, {
      App: (configuration: { globalData: Record<string, unknown> }) => { application = configuration; },
      console,
    });
    assert.ok(application);
    let page: Record<string, unknown> | undefined;
    const pageScript = Object.entries(project.files).find(([path]) => /^pages\/.+\.js$/u.test(path))?.[1];
    assert.ok(pageScript);
    runInNewContext(pageScript, {
      Page: (configuration: Record<string, unknown>) => { page = configuration; },
      getApp: () => application,
      console,
    });
    assert.ok(page);
    const instance = {
      ...page,
      data: JSON.parse(JSON.stringify(page.data)) as Record<string, unknown>,
      setData(patch: Record<string, unknown>) { Object.assign(this.data, patch); },
    } as Record<string, unknown> & { data: Record<string, unknown>; setData: (patch: Record<string, unknown>) => void };
    (page.onLoad as (this: typeof instance, options: Record<string, unknown>) => void).call(instance, { scene: "test" });
    (page.handleInput0 as (this: typeof instance, event: unknown) => void).call(instance, { detail: { value: "  buy milk  " } });
    assert.equal(instance.data.canSubmit0, true);
    (page.handleSubmit0 as (this: typeof instance) => void).call(instance);
    assert.deepEqual(JSON.parse(JSON.stringify(instance.data.items)), ["buy milk"]);
    assert.deepEqual(JSON.parse(JSON.stringify(instance.data.itemsRender)), [{ value: "buy milk", __elmosKey: "buy milk-0" }]);
    assert.deepEqual(JSON.parse(JSON.stringify(application!.globalData.items)), ["buy milk"]);
    assert.equal(instance.data.title, "");
    assert.equal(instance.data.canSubmit0, false);
    (page.handleInput0 as (this: typeof instance, event: unknown) => void).call(instance, { detail: { value: "   " } });
    (page.handleSubmit0 as (this: typeof instance) => void).call(instance);
    assert.deepEqual(JSON.parse(JSON.stringify(instance.data.items)), ["buy milk"]);
  }

  const nestedLabelFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      '<button :disabled="!title.trim()" @click="submit">Add</button>',
      '<button :disabled="!title.trim()" @click="submit"><span>Add</span></button>',
    ),
  } : file);
  const nestedLabelRun = runMiniappConversion(conversionInput(nestedLabelFiles, "vue3", ["wechat"]));
  const nestedTemplate = Object.entries(nestedLabelRun.generatedProjects[0]!.files)
    .find(([path]) => path.endsWith(".wxml"))?.[1] ?? "";
  assert.match(nestedTemplate, />Add<\/button>/u);
  assert.doesNotMatch(nestedTemplate, />Submit<\/button>/u);
});

test("unrequested target generator remains not applicable through the Skill handler", async () => {
  const { executeMiniappSkill } = await import("../src/miniapp-skill-runtime.js");
  const input = conversionInput(undefined, undefined, ["wechat"]);
  const result = executeMiniappSkill("alipay-miniapp-codegen", input);
  assert.equal(result.state, "NOT_APPLICABLE");
  assert.deepEqual(result.payload, { state: "NOT_APPLICABLE", platform: "alipay" });

  const run = runMiniappConversion(input);
  const taskStates = new Map(run.taskRecords.map(record => [record.taskId, record.state]));
  assert.equal(taskStates.get("MAPP-023"), "EXECUTED_LOCAL");
  assert.equal(taskStates.get("MAPP-024"), "NOT_APPLICABLE");
  assert.equal(taskStates.get("MAPP-025"), "NOT_APPLICABLE");
  assert.equal(taskStates.get("MAPP-026"), "NOT_APPLICABLE");
});
