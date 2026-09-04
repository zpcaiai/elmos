import type { NextConfig } from "next";
import path from "node:path";

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
  serverExternalPackages: ["html-to-text", "mammoth", "pdfjs-dist"],
  experimental: {
    externalDir: true,
  },
  turbopack: {
    root: path.resolve(__dirname, "../.."),
  },
  outputFileTracingIncludes: {
    "/api/**/*": [
      "../../routes/**/*",
      "../../pom.xml",
      "../../engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json",
    ],
  },
  async redirects() {
    return [
      {
        source: "/skills",
        destination: "/capabilities",
        permanent: true,
      },
      {
        source: "/skills/:path*",
        destination: "/capabilities",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
