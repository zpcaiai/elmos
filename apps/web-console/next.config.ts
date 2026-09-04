import type { NextConfig } from "next";
import path from "node:path";

const configuredDistDir = process.env.ELMOS_NEXT_DIST_DIR;
if (
  configuredDistDir
  && configuredDistDir !== ".next"
  && !/^\.next-e2e-\d{4,5}(?:-[0-9a-f]{16})?$/.test(configuredDistDir)
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
    "/api/capabilities/translation": [
      "../../routes/inventory.json",
      "../../routes/*/route.json",
      "../../routes/*/support-matrix.json",
      "../../routes/*/certification/certification.json",
      "../../routes/*/certification/evidence.json",
      "../../pom.xml",
    ],
    "/api/translation/**/*": [
      "../../routes/inventory.json",
      "../../routes/*/route.json",
      "../../routes/*/support-matrix.json",
      "../../routes/*/certification/certification.json",
      "../../routes/*/certification/evidence.json",
      "../../pom.xml",
    ],
    "/api/capabilities/database-sql": [
      "../../engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json",
    ],
    "/api/database-sql/**/*": [
      "../../engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json",
    ],
    "/api/capabilities/spring": [
      "../../pom.xml",
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
