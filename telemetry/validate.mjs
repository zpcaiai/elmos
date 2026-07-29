import { readFile } from "node:fs/promises";

const policy = JSON.parse(await readFile(new URL("./policy.json", import.meta.url), "utf8"));
const schema = JSON.parse(await readFile(new URL("./events.schema.json", import.meta.url), "utf8"));
const metrics = JSON.parse(await readFile(new URL("./metric-definitions.json", import.meta.url), "utf8"));
const leakFixtures = JSON.parse(await readFile(new URL("./leak-fixtures.json", import.meta.url), "utf8"));

if (policy.schemaVersion !== schema.properties.schemaVersion.const) {
  throw new Error("telemetry schema versions drifted");
}
if (policy.eventNames.length !== schema.properties.eventName.enum.length
  || !policy.eventNames.every((name) => schema.properties.eventName.enum.includes(name))) {
  throw new Error("telemetry event names drifted");
}
if (
  policy.allowedDimensions.length === 0
  || policy.approvedQuestions.length === 0
  || policy.fieldChangeCollection !== "PROHIBITED"
  || policy.individualProductivityScoring !== "PROHIBITED"
) {
  throw new Error("telemetry purpose or trust boundary drifted");
}
for (const businessLine of [
  "overview", "spring", "translation", "generation", "repositories",
  "migration", "commercialization", "pricing", "skills", "admin",
]) {
  if (!schema.properties.businessLine.enum.includes(businessLine)) {
    throw new Error(`telemetry business line missing: ${businessLine}`);
  }
}
for (const fixture of leakFixtures.forbiddenPayloads) {
  for (const key of Object.keys(fixture)) {
    if (schema.properties[key] || !policy.forbiddenFields.includes(key)) {
      throw new Error(`forbidden telemetry fixture is not blocked: ${key}`);
    }
  }
}
if (
  !metrics.definitions.failure_rate_bps.population.includes("raw clicks")
  || !metrics.definitions.active_sessions.population.includes("product_telemetry")
) {
  throw new Error("telemetry metrics can be distorted by raw interaction or audit request volume");
}
if (
  policy.rawEventRetentionDaysTarget !== 30
  || policy.automaticPruneAvailable !== true
  || policy.automaticPruneDefaultEnabled !== false
  || policy.deletionScope !== "product_telemetry_events_only"
  || policy.appendOnlyAuditDeleted !== false
) {
  throw new Error("telemetry retention or immutable audit boundaries drifted");
}
if (schema.additionalProperties !== false || policy.productionRetentionEvidence !== "NOT_RUN") {
  throw new Error("telemetry contract is not fail closed");
}

console.log(
  `telemetry policy ${policy.schemaVersion}: ${policy.eventNames.length} events, `
  + `${policy.metrics.length} metrics, ${policy.rawEventRetentionDaysTarget}d governed retention, production ${policy.productionRetentionEvidence}`,
);
