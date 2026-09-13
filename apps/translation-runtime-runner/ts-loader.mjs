// Trusted image-side loader. It never evaluates repository loaders or hooks.
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../web-console/package.json', import.meta.url));
const ts = require('typescript');
export async function resolve(specifier, context, next) {
  try { return await next(specifier, context); }
  catch (error) {
    if (error?.code !== 'ERR_MODULE_NOT_FOUND' || !specifier.startsWith('.') || /\.[a-z0-9]+$/i.test(specifier)) throw error;
    return next(`${specifier}.ts`, context);
  }
}
export async function load(url, context, next) {
  if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: `export default ${await readFile(new URL(url), 'utf8')};` };
  if (!url.endsWith('.ts')) return next(url, context);
  return { format: 'module', shortCircuit: true, source: ts.transpileModule(await readFile(new URL(url), 'utf8'), {
    fileName: new URL(url).pathname,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, isolatedModules: true },
  }).outputText };
}
