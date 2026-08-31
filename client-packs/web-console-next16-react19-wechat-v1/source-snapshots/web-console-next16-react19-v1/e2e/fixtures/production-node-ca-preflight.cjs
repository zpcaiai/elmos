const { existsSync } = require("node:fs");
const tls = require("node:tls");

const certificatePath = process.env.NODE_EXTRA_CA_CERTS ?? "";
if (!certificatePath || !existsSync(certificatePath)) {
  throw new Error("ELMOS_E2E_PRODUCTION_OIDC_CA_FILE_REQUIRED");
}
if (typeof tls.getCACertificates !== "function" || tls.getCACertificates("extra").length !== 1) {
  throw new Error("ELMOS_E2E_PRODUCTION_OIDC_CA_NOT_LOADED");
}
process.stderr.write(`ELMOS production OIDC CA preflight PASS pid=${process.pid}\n`);
