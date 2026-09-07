#!/usr/bin/env node
import {
  materializeFrontendInteractionCampaign,
  verifyFrontendInteractionCampaign,
} from "./frontend-interaction-formal-equivalence.js";

const expectedProofProfile = "bounded-frontend-interaction-v1";

function option(args: readonly string[], name: string): string | undefined {
  const indexes = args.flatMap((value, index) => value === name ? [index] : []);
  if (indexes.length > 1) throw new Error(`${name} may be supplied only once`);
  const index = indexes[0];
  if (index === undefined) return undefined;
  const value = args[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${name} requires a value`);
  return value;
}

function main(): void {
  const args = process.argv.slice(2);
  const allowed = new Set(["--proof-profile", "--output", "--verify", "--solver", "--json"]);
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index]!;
    if (!value.startsWith("--")) continue;
    if (!allowed.has(value)) throw new Error(`unknown frontend interaction option: ${value}`);
    if (value !== "--json") index += 1;
  }
  const proofProfile = option(args, "--proof-profile");
  if (proofProfile !== expectedProofProfile) {
    throw new Error(`--proof-profile ${expectedProofProfile} is required; missing, unknown, and downgrade profiles fail closed`);
  }
  const output = option(args, "--output"); const verify = option(args, "--verify");
  if ((output === undefined) === (verify === undefined)) throw new Error("use exactly one of --output <dir> or --verify <dir>");
  const solver = option(args, "--solver");
  const json = args.includes("--json");
  if (verify !== undefined) {
    const errors = verifyFrontendInteractionCampaign(verify, solver === undefined ? {} : { solver: { command: solver } });
    const result = { schema_version: "1.0", kind: "frontend-interaction-formal-campaign-verification", proof_profile: expectedProofProfile, valid: errors.length === 0, errors };
    process.stdout.write(json ? `${JSON.stringify(result)}\n` : `${JSON.stringify(result, null, 2)}\n`);
    if (errors.length > 0) process.exitCode = 2;
    return;
  }
  const campaign = materializeFrontendInteractionCampaign(output!, solver === undefined ? {} : { solver: { command: solver } });
  process.stdout.write(json ? `${JSON.stringify(campaign)}\n` : `${JSON.stringify(campaign, null, 2)}\n`);
  const routes = campaign.routes;
  if (!Array.isArray(routes) || routes.some(route => (route as Record<string, unknown>).status !== "PROVED_UNDER_ASSUMPTIONS")) process.exitCode = 2;
}

try { main(); } catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1;
}
