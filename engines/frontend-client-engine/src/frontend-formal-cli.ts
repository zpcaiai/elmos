#!/usr/bin/env node
import { materializeFrontendFormalCampaign, verifyFrontendFormalCampaign } from "./frontend-formal-equivalence.js";

function option(args: readonly string[], name: string): string | undefined {
  const index = args.indexOf(name);
  if (index < 0) return undefined;
  const value = args[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${name} requires a value`);
  return value;
}

function main(): void {
  const args = process.argv.slice(2);
  const output = option(args, "--output");
  const verify = option(args, "--verify");
  const json = args.includes("--json");
  if ((output === undefined) === (verify === undefined)) {
    throw new Error("use exactly one of --output <dir> or --verify <dir>");
  }
  if (verify !== undefined) {
    const errors = verifyFrontendFormalCampaign(verify);
    const result = { schema_version: "1.0", kind: "frontend-formal-campaign-verification", valid: errors.length === 0, errors };
    process.stdout.write(json ? `${JSON.stringify(result)}\n` : `${JSON.stringify(result, null, 2)}\n`);
    if (errors.length > 0) process.exitCode = 2;
    return;
  }
  const solver = option(args, "--solver");
  const campaign = materializeFrontendFormalCampaign(output!, solver === undefined ? {} : { solver: { command: solver } });
  process.stdout.write(json ? `${JSON.stringify(campaign)}\n` : `${JSON.stringify(campaign, null, 2)}\n`);
  const routes = campaign.routes;
  if (!Array.isArray(routes) || routes.some(route => (route as Record<string, unknown>).status !== "PROVED_UNDER_ASSUMPTIONS")) {
    process.exitCode = 2;
  }
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
