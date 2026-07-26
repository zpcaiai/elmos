import type { NextConfig } from "next";

const configuredDistDir = process.env.ELMOS_NEXT_DIST_DIR;
if (
  configuredDistDir
  && configuredDistDir !== ".next"
  && !/^\.next-e2e-\d{4,5}$/.test(configuredDistDir)
) {
  throw new Error("ELMOS_NEXT_DIST_DIR_INVALID");
}

const nextConfig: NextConfig = {
  distDir: configuredDistDir ?? ".next",
};

export default nextConfig;
