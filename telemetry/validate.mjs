import { readFile } from "node:fs/promises";

const policy = JSON.parse(await readFile(new URL("./policy.json", import.meta.url), "utf8"));
const schema = JSON.parse(await readFile(new URL("./events.schema.json", import.meta.url), "utf8"));

if (policy.schemaVersion !== schema.properties.schemaVersion.const) {
  throw new Error("telemetry schema versions drifted");
}
if (policy.eventNames.length !== schema.properties.eventName.enum.length
  || !policy.eventNames.every((name) => schema.properties.eventName.enum.includes(name))) {
  throw new Error("telemetry event names drifted");
}
if (policy.rawEventRetentionDaysTarget !== 30 || policy.automaticPruneEnabled !== false) {
  throw new Error("telemetry retention must remain an explicit NOT_RUN operational gate");
}
if (schema.additionalProperties !== false || policy.productionRetentionEvidence !== "NOT_RUN") {
  throw new Error("telemetry contract is not fail closed");
}

console.log(
  `telemetry policy ${policy.schemaVersion}: ${policy.eventNames.length} events, `
  + `${policy.metrics.length} metrics, ${policy.rawEventRetentionDaysTarget}d target, production ${policy.productionRetentionEvidence}`,
);
