import {
  constants,
  closeSync,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
} from "node:fs";
import { createHash, createHmac, randomUUID } from "node:crypto";
import path from "node:path";

const runId = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const requestPathPattern = new RegExp(
  `^/engine/v1/spring-upgrades(?:/(?:capabilities|${runId}(?:/(?:logs|artifact|retry|cancel|runtime/(?:start|stop)))?))?$`,
);
const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const actorPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$/;
const authenticationProtocol = "ELMOS-SPRING-ENGINE-HMAC-V1";
const authenticationRole = "ENGINE";

type SignInput = {
  method: string;
  requestPath: string;
  organizationId: string;
  actorId: string;
  body: string;
  secret: Buffer;
  timestamp: number;
  nonce: string;
};

function sha256(value: Buffer | string) {
  return createHash("sha256").update(value).digest("hex");
}

export function signSpringEngineRequest(input: SignInput) {
  const method = input.method.toUpperCase();
  if (!["GET", "POST"].includes(method)) throw new Error("SPRING_ENGINE_METHOD_REJECTED");
  if (!requestPathPattern.test(input.requestPath)) throw new Error("SPRING_ENGINE_PATH_REJECTED");
  if (!organizationPattern.test(input.organizationId)) throw new Error("SPRING_ENGINE_ORGANIZATION_REJECTED");
  if (!actorPattern.test(input.actorId)) throw new Error("SPRING_ENGINE_ACTOR_REJECTED");
  if (!Number.isSafeInteger(input.timestamp) || input.timestamp <= 0) {
    throw new Error("SPRING_ENGINE_TIMESTAMP_REJECTED");
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(input.nonce)) {
    throw new Error("SPRING_ENGINE_NONCE_REJECTED");
  }
  if (input.secret.byteLength < 32 || input.secret.byteLength > 4_096) {
    throw new Error("SPRING_ENGINE_SECRET_REJECTED");
  }
  const bodySha256 = sha256(input.body);
  const canonical = [
    authenticationProtocol,
    authenticationRole,
    String(input.timestamp),
    input.nonce,
    method,
    input.requestPath,
    input.organizationId,
    input.actorId,
    bodySha256,
  ].join("\n");
  return {
    timestamp: String(input.timestamp),
    nonce: input.nonce,
    bodySha256,
    signature: createHmac("sha256", input.secret).update(canonical).digest("hex"),
  };
}

function configuredSecret(): Buffer {
  const configured = process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE?.trim() ?? "";
  if (
    !configured
    || !path.isAbsolute(configured)
    || path.normalize(configured) !== configured
  ) {
    throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_REQUIRED");
  }
  let descriptor: number | undefined;
  try {
    for (
      let parent = path.dirname(configured);
      parent !== path.dirname(parent);
      parent = path.dirname(parent)
    ) {
      if (lstatSync(parent).isSymbolicLink()) {
        throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED");
      }
    }
    const before = lstatSync(configured);
    const currentUid = typeof process.getuid === "function" ? process.getuid() : before.uid;
    if (
      !before.isFile()
      || before.nlink !== 1
      || before.uid !== currentUid
      || before.size < 32
      || before.size > 4_096
      || ![0o400, 0o600].includes(before.mode & 0o777)
    ) {
      throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED");
    }
    const closeOnExec = (
      constants as typeof constants & { O_CLOEXEC?: number }
    ).O_CLOEXEC ?? 0;
    descriptor = openSync(
      /*turbopackIgnore: true*/ configured,
      constants.O_RDONLY | constants.O_NOFOLLOW | closeOnExec,
    );
    const details = fstatSync(descriptor);
    if (
      !details.isFile()
      || details.dev !== before.dev
      || details.ino !== before.ino
      || details.nlink !== 1
      || details.uid !== currentUid
      || details.size < 32
      || details.size > 4_096
      || ![0o400, 0o600].includes(details.mode & 0o777)
    ) {
      throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED");
    }
    const secret = readFileSync(/*turbopackIgnore: true*/ descriptor);
    const decodedSecret = secret.toString("utf8");
    const completed = fstatSync(descriptor);
    const pathAfter = lstatSync(configured);
    if (
      secret.byteLength !== details.size
      || completed.dev !== details.dev
      || completed.ino !== details.ino
      || completed.mode !== details.mode
      || completed.uid !== details.uid
      || completed.gid !== details.gid
      || completed.nlink !== details.nlink
      || completed.size !== details.size
      || completed.mtimeMs !== details.mtimeMs
      || completed.ctimeMs !== details.ctimeMs
      || pathAfter.dev !== details.dev
      || pathAfter.ino !== details.ino
      || pathAfter.mode !== details.mode
      || pathAfter.uid !== details.uid
      || pathAfter.gid !== details.gid
      || pathAfter.nlink !== details.nlink
      || pathAfter.size !== details.size
      || !Buffer.from(decodedSecret, "utf8").equals(secret)
      || /^\s|\s$/u.test(decodedSecret)
    ) {
      throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED");
    }
    return secret;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("SPRING_ENGINE_")) throw error;
    throw new Error("SPRING_ENGINE_AUTH_SECRET_FILE_UNAVAILABLE");
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

export function authenticateSpringEngineRequest(
  method: "GET" | "POST",
  requestPath: string,
  originalHeaders: HeadersInit,
  body = "",
) {
  const headers = new Headers(originalHeaders);
  if (process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED !== "true") return headers;
  const organizationId = headers.get("X-ELMOS-Organization-ID") ?? "";
  const actorId = headers.get("X-ELMOS-Actor-ID") ?? "";
  const signed = signSpringEngineRequest({
    method,
    requestPath,
    organizationId,
    actorId,
    body,
    secret: configuredSecret(),
    timestamp: Math.floor(Date.now() / 1_000),
    nonce: randomUUID(),
  });
  headers.set("X-ELMOS-Engine-Timestamp", signed.timestamp);
  headers.set("X-ELMOS-Engine-Nonce", signed.nonce);
  headers.set("X-ELMOS-Engine-Body-SHA256", signed.bodySha256);
  headers.set("X-ELMOS-Engine-Signature", signed.signature);
  return headers;
}
