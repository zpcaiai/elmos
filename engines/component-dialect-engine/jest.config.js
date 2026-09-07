/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  testMatch: ["<rootDir>/tests/**/*.test.ts"],
  // The execution leg and the Angular/Svelte subprocess checks write scratch
  // files under .cde-scratch so Node can resolve `react` / `vue` /
  // `@angular/*` from this package's node_modules.
  modulePathIgnorePatterns: ["<rootDir>/.cde-scratch/"],
  // Real toolchains are slow; the direction matrix drives 54 pairs through
  // actual compilers and server renderers.
  testTimeout: 60000,
  // Every test completes, but Node's ESM loader keeps a handle alive after
  // the subprocess renders, so the worker does not exit on its own. The
  // assertions have already run and reported by this point.
  forceExit: true,
};
