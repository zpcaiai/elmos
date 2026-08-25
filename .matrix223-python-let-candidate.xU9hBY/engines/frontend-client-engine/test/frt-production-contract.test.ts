import test from "node:test";
import assert from "node:assert/strict";

import { frtCatalog } from "../src/frt-catalog.generated.js";
import {
  assertFRTContractRegistry,
  digestFrtExecutionContract,
  frtExecutionContractByKey,
  validateFrtProductionInput,
} from "../src/frt-production-contract.js";

const validInputByHandler: Readonly<Record<string, Readonly<Record<string, unknown>>>> = {
  governance: { invariants: [] },
  estate_discovery: { files: { "src/App.tsx": "export const App = () => null;" } },
  semantic_ir: { files: { "src/App.tsx": "export const App = () => null;" } },
  typed_contract: { files: { "src/App.tsx": "export const App = () => null;" } },
  migration_planning: { inventory: {}, target: {} },
  source_generation: { targetProfile: {}, uiIr: {} },
  build_toolchain: { astNodes: [] },
  test_automation: { components: [] },
  delivery_pipeline: { states: [] },
  design_system: { routes: [] },
  mobile_client: { uiNodes: [] },
  cross_platform: { requiredCapabilities: [], platformCapabilities: {} },
  directional_route: { files: { "src/App.tsx": "export const App = () => null;" } },
  route_orchestration: { corpus: [] },
  compatibility: { packs: [] },
  advanced_verification: { properties: [] },
  runtime_operations: { resources: [] },
  product_workflow: { requirements: [], states: [], transitions: [] },
  administration: { capabilities: [], roles: [], operations: [] },
  performance_capacity: { workload: {}, budgets: {} },
  resilience_dr: { scenarios: [], recoveryObjectives: {} },
  security_privacy: { assets: [], findings: [] },
  production_readiness: { slos: [], runbooks: [] },
};

test("all 472 canonical Skills compile to distinct production execution contracts", () => {
  assert.doesNotThrow(() => assertFRTContractRegistry());
  const contracts = frtCatalog.skills.map(skill => skill.executionContract);
  assert.equal(contracts.length, 472);
  assert.equal(new Set(contracts.map(contract => contract.capabilityKey)).size, 472);
  assert.equal(new Set(contracts.map(contract => contract.contractDigest)).size, 472);
  for (const contract of contracts) {
    assert.equal(contract.requiredSurfaces.length, 6, contract.skillId);
    assert.equal(new Set(contract.requiredSurfaces).size, 6, contract.skillId);
    assert.equal(contract.apiOperations.length, 5, contract.skillId);
    assert.equal(contract.outputContracts.length, 4, contract.skillId);
    assert.ok(contract.outputContracts.every(output => output.startsWith(contract.skillId)));
    assert.equal(contract.inputContract.additionalProperties, false);
    assert.equal(contract.productionOperationAuthority, "EXTERNAL_ONLY");
    assert.equal(contract.certification, "NOT_CERTIFIED");
    assert.equal(digestFrtExecutionContract(contract), contract.contractDigest);
  }
});

test("every handler family accepts its exact declared top-level contract", () => {
  const handlerKinds = new Set(frtCatalog.skills.map(skill => skill.handlerKind));
  assert.deepEqual(new Set(Object.keys(validInputByHandler)), handlerKinds);
  for (const skill of frtCatalog.skills) {
    const input = validInputByHandler[skill.handlerKind];
    assert.ok(input, skill.handlerKind);
    assert.deepEqual(
      validateFrtProductionInput(skill.executionContract, "ANALYZE", input),
      [],
      skill.id,
    );
  }
});

test("the same contract is resolved by immutable ID and source name", () => {
  const skill = frtCatalog.skills[137]!;
  assert.equal(frtExecutionContractByKey(skill.id)?.contractDigest, skill.executionContract.contractDigest);
  assert.equal(frtExecutionContractByKey(skill.name)?.contractDigest, skill.executionContract.contractDigest);
  assert.equal(frtExecutionContractByKey("FRT-9999"), undefined);
});

test("production input validation rejects omissions, unknown fields, mutable VERIFY input, and unsafe source paths", () => {
  const governance = frtCatalog.skills.find(skill => skill.handlerKind === "governance")!;
  assert.ok(validateFrtProductionInput(governance.executionContract, "EXECUTE", {})
    .some(item => item.code === "FRT_HANDLER_INPUT_REQUIRED"));
  assert.ok(validateFrtProductionInput(governance.executionContract, "ANALYZE", {
    invariants: [], unexpected: true,
  }).some(item => item.code === "FRT_HANDLER_INPUT_UNKNOWN"));
  assert.equal(
    validateFrtProductionInput(governance.executionContract, "VERIFY", { invariants: [] })[0]?.code,
    "FRT_VERIFY_INPUT_NOT_ALLOWED",
  );

  const source = frtCatalog.skills.find(skill => skill.handlerKind === "estate_discovery")!;
  assert.ok(validateFrtProductionInput(source.executionContract, "ANALYZE", {
    files: { "../secrets.txt": "blocked" },
  }).some(item => item.code === "FRT_SOURCE_PATH_INVALID"));
});

test("production input validation is bounded against deep and non-JSON objects", () => {
  const skill = frtCatalog.skills.find(item => item.handlerKind === "governance")!;
  let deep: Record<string, unknown> = { invariants: [] };
  for (let index = 0; index < 40; index += 1) deep = { invariants: [], nested: deep };
  assert.ok(validateFrtProductionInput(skill.executionContract, "PLAN", deep)
    .some(item => item.code === "FRT_INPUT_DEPTH_EXCEEDED"));

  const nonPlain = Object.create({ inherited: true }) as Record<string, unknown>;
  nonPlain.invariants = [];
  assert.ok(validateFrtProductionInput(skill.executionContract, "ANALYZE", nonPlain)
    .some(item => item.code === "FRT_INPUT_OBJECT_PROTOTYPE_REJECTED"));
});
