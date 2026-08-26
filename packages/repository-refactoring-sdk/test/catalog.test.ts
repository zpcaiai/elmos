import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { CATALOG_RELATIVE_PATH, type CatalogDocument } from "../src/catalog-source.js";
import {
  CATALOG_VERSION,
  SKILL_NAMES,
  SKILL_SPECS,
  isDependencyOrdered,
  pendingSkills,
  topologicalOrder,
} from "../src/catalog.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const document = JSON.parse(
  readFileSync(resolve(packageRoot, CATALOG_RELATIVE_PATH), "utf8"),
) as CatalogDocument;

test("the generated catalog has not drifted from the core's own", () => {
  assert.deepEqual([...SKILL_NAMES], document.skills.map((skill) => skill.name));
  assert.equal(CATALOG_VERSION, document.package_version);
  for (const skill of document.skills) {
    const spec = SKILL_SPECS[skill.name as (typeof SKILL_NAMES)[number]];
    assert.ok(spec, `${skill.name} is missing from the generated specs`);
    assert.equal(spec.handler, skill.handler);
    assert.equal(spec.riskClass, skill.risk_class);
    assert.equal(spec.mutating, skill.mutating);
    assert.equal(spec.implemented, skill.implemented);
    assert.deepEqual([...spec.dependsOn], [...skill.depends_on]);
  }
});

test("declaration order is NOT dependency order, and the SDK does not pretend it is", () => {
  //: 09 data-schema-refactor depends on 17 human-approval-gate.  A host that
  //: scheduled in catalog order would run it before the gate exists.
  assert.equal(isDependencyOrdered(SKILL_NAMES), false);
});

test("topologicalOrder() places every Skill after its dependencies", () => {
  const order = topologicalOrder();
  assert.equal(order.length, SKILL_NAMES.length);
  assert.deepEqual([...order].sort(), [...SKILL_NAMES].sort());
  assert.equal(isDependencyOrdered(order), true);
});

test("every dependency names a Skill that exists", () => {
  const known = new Set<string>(SKILL_NAMES);
  for (const name of SKILL_NAMES) {
    for (const dependency of SKILL_SPECS[name].dependsOn) {
      assert.ok(known.has(dependency), `${name} depends on unknown '${dependency}'`);
    }
  }
});

test("no Skill is still pending a production handler", () => {
  assert.deepEqual([...pendingSkills()], []);
  assert.equal(SKILL_NAMES.length, 23);
});
