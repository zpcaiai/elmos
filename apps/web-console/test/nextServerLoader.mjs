// Loader for unit tests that import API route handlers directly. Route
// handlers import NextRequest/NextResponse from "next/server", which only
// resolves inside the Next.js bundler; in plain node tests we redirect that
// specifier to a minimal stub with the same runtime surface the handlers
// use (NextResponse.json with status/headers). Everything else - including
// the extensionless TypeScript resolution - reuses the repo loader.
import { resolve as tsResolve, load as tsLoad } from "./ts-extension-loader.mjs";

const stubUrl = new URL("./stubs/nextServer.mjs", import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "next/server") {
    return { url: stubUrl, shortCircuit: true, format: "module" };
  }
  return tsResolve(specifier, context, nextResolve);
}

export async function load(url, context, nextLoad) {
  return tsLoad(url, context, nextLoad);
}
