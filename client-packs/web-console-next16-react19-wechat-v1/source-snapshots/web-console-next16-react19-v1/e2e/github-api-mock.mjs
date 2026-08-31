import { createHash } from "node:crypto";
import { createServer } from "node:http";

const port = Number.parseInt(process.env.ELMOS_E2E_GITHUB_PORT ?? "3299", 10);
const expectedToken = "github-e2e-fine-grained-token-32-characters";
const repositories = new Map();
const creationAttempts = new Map();
const deletionAttempts = new Map();
const unknownIdentityRepository = "reconcile-unknown-service";
const corruptBlobRepository = "blob-corrupt-service";
const oversizedBlobRepository = "blob-oversized-service";
const oversizedJsonRepository = "json-oversized-service";
const oversizedDeclaredJsonRepository = "json-declared-oversized-service";
const slowBlobRepository = "slow-publish-service";
const recoveredMarkerRepository = "recovered-marker-service";
const spoofedRepositoryUrlRepository = "html-url-spoof-service";
let nextRepositoryId = 1_000;
let providerRequestCount = 0;

function send(response, status, value, declaredLength = true) {
  const body = value === undefined ? Buffer.alloc(0) : Buffer.from(JSON.stringify(value));
  response.writeHead(status, {
    "Content-Type": "application/json",
    ...(declaredLength ? { "Content-Length": String(body.length) } : {}),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

function sendRaw(response, body, declaredLength = true) {
  response.writeHead(200, {
    "Content-Type": "application/octet-stream",
    ...(declaredLength ? { "Content-Length": String(body.length) } : {}),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

async function jsonBody(request) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > 80 * 1024 * 1024) throw new Error("BODY_TOO_LARGE");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf-8") || "{}");
}

function digest(value) {
  return createHash("sha1").update(value).digest("hex");
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { status: "UP" });
    return;
  }
  if (request.headers.authorization !== `Bearer ${expectedToken}`) {
    send(response, 401, { message: "credential rejected" });
    return;
  }
  try {
    if (!url.pathname.startsWith("/__test/")) providerRequestCount += 1;
    if (request.method === "GET" && url.pathname === "/user") {
      send(response, 200, { login: "elmos-e2e" });
      return;
    }
    if (request.method === "GET" && url.pathname === "/__test/state") {
      const fullName = url.searchParams.get("full_name") ?? "";
      const repository = repositories.get(fullName);
      send(response, 200, {
        full_name: fullName,
        exists: Boolean(repository),
        repository_id: repository?.id ?? null,
        creation_attempts: creationAttempts.get(fullName) ?? 0,
        deletion_attempts: deletionAttempts.get(fullName) ?? 0,
      });
      return;
    }
    if (request.method === "GET" && url.pathname === "/__test/metrics") {
      send(response, 200, { provider_requests: providerRequestCount });
      return;
    }
    if (request.method === "POST" && url.pathname === "/__test/seed-recovery-repository") {
      const body = await jsonBody(request);
      const fullName = `elmos-e2e/${recoveredMarkerRepository}`;
      if (
        body.full_name !== fullName
        || typeof body.description !== "string"
        || !body.description.includes("ELMOS-Publication-ID:")
        || !body.description.includes("Artifact-SHA256:")
      ) {
        send(response, 400, { message: "invalid recovery fixture" });
        return;
      }
      repositories.set(fullName, {
        id: nextRepositoryId++,
        owner: "elmos-e2e",
        name: recoveredMarkerRepository,
        description: body.description,
        defaultBranch: "",
        blobs: new Map(),
        tree: [],
        commit: "",
        branch: "",
      });
      send(response, 201, { full_name: fullName });
      return;
    }
    if (request.method === "POST" && (url.pathname === "/user/repos" || /^\/orgs\/[^/]+\/repos$/.test(url.pathname))) {
      const body = await jsonBody(request);
      const owner = url.pathname === "/user/repos"
        ? "elmos-e2e"
        : decodeURIComponent(url.pathname.split("/")[2]);
      const fullName = `${owner}/${body.name}`;
      creationAttempts.set(fullName, (creationAttempts.get(fullName) ?? 0) + 1);
      if (repositories.has(fullName) || body.private !== true || body.auto_init !== false) {
        send(response, 422, { message: "repository exists or is not private" });
        return;
      }
      const repository = {
        id: nextRepositoryId++,
        owner,
        name: body.name,
        description: body.description,
        defaultBranch: "",
        blobs: new Map(),
        tree: [],
        commit: "",
        branch: "",
      };
      repositories.set(fullName, repository);
      if (body.name === unknownIdentityRepository) {
        send(response, 201, {
          id: "identity-not-confirmed",
          name: body.name,
          full_name: fullName,
          html_url: `https://github.example.invalid/${fullName}`,
          private: true,
          default_branch: repository.defaultBranch,
          description: repository.description,
          owner: { login: owner },
        });
        return;
      }
      if (body.name === spoofedRepositoryUrlRepository) {
        send(response, 201, {
          id: repository.id,
          name: body.name,
          full_name: fullName,
          html_url: `https://attacker.example.invalid/${fullName}`,
          private: true,
          default_branch: repository.defaultBranch,
          description: repository.description,
          owner: { login: owner },
        });
        return;
      }
      send(response, 201, {
        id: repository.id,
        name: body.name,
        full_name: fullName,
        html_url: `https://github.example.invalid/${fullName}`,
        private: true,
        default_branch: repository.defaultBranch,
        description: repository.description,
        owner: { login: owner },
      });
      return;
    }

    const match = url.pathname.match(/^\/repos\/([^/]+)\/([^/]+)(\/.*)?$/);
    if (!match) {
      send(response, 404, { message: "not found" });
      return;
    }
    const owner = decodeURIComponent(match[1]);
    const name = decodeURIComponent(match[2]);
    const suffix = match[3] ?? "";
    const fullName = `${owner}/${name}`;
    const repository = repositories.get(fullName);
    if (!repository) {
      send(response, 404, { message: "not found" });
      return;
    }
    if (request.method === "GET" && suffix === "") {
      send(response, 200, {
        id: repository.id,
        name: repository.name,
        full_name: fullName,
        html_url: `https://github.example.invalid/${fullName}`,
        private: true,
        default_branch: repository.defaultBranch,
        description: repository.description,
        owner: { login: owner },
      });
      return;
    }
    if (request.method === "DELETE" && suffix === "") {
      deletionAttempts.set(fullName, (deletionAttempts.get(fullName) ?? 0) + 1);
      repositories.delete(fullName);
      send(response, 204, undefined);
      return;
    }
    if (request.method === "POST" && suffix === "/git/blobs") {
      const body = await jsonBody(request);
      if (body.encoding !== "base64" || typeof body.content !== "string") {
        send(response, 422, { message: "invalid blob" });
        return;
      }
      const content = Buffer.from(body.content, "base64");
      const sha = digest(Buffer.concat([Buffer.from(`blob ${content.length}\0`), content]));
      repository.blobs.set(sha, content);
      if (name === slowBlobRepository && repository.slowBlobDelayed !== true) {
        repository.slowBlobDelayed = true;
        await new Promise((resolve) => setTimeout(resolve, 3_000));
      }
      if (name === oversizedJsonRepository) {
        send(response, 201, { sha, padding: "x".repeat(2 * 1024 * 1024) }, false);
        return;
      }
      if (name === oversizedDeclaredJsonRepository) {
        send(response, 201, { sha, padding: "x".repeat(2 * 1024 * 1024) });
        return;
      }
      send(response, 201, { sha });
      return;
    }
    if (request.method === "GET" && suffix.startsWith("/git/blobs/")) {
      if (!request.headers.accept?.includes("application/vnd.github.raw+json")) {
        send(response, 406, { message: "raw blob media type required" });
        return;
      }
      const sha = suffix.slice("/git/blobs/".length);
      const stored = repository.blobs.get(sha);
      if (!stored) {
        send(response, 404, { message: "blob not found" });
        return;
      }
      if (name === corruptBlobRepository) {
        const corrupted = Buffer.from(stored.length > 0 ? stored : Buffer.from([0]));
        corrupted[0] ^= 0xff;
        sendRaw(response, corrupted);
        return;
      }
      if (name === oversizedBlobRepository) {
        sendRaw(response, Buffer.concat([stored, Buffer.alloc(64 * 1024, 0x78)]), false);
        return;
      }
      sendRaw(response, stored);
      return;
    }
    if (request.method === "POST" && suffix === "/git/trees") {
      const body = await jsonBody(request);
      if (!Array.isArray(body.tree) || body.tree.length === 0 || body.tree.some((entry) => !repository.blobs.has(entry.sha))) {
        send(response, 422, { message: "invalid tree" });
        return;
      }
      repository.tree = body.tree;
      repository.treeSha = digest(JSON.stringify(body.tree));
      send(response, 201, { sha: repository.treeSha });
      return;
    }
    if (request.method === "POST" && suffix === "/git/commits") {
      const body = await jsonBody(request);
      if (body.tree !== repository.treeSha || !Array.isArray(body.parents) || body.parents.length !== 0) {
        send(response, 422, { message: "invalid commit" });
        return;
      }
      repository.commit = digest(`${body.message}\n${body.tree}`);
      send(response, 201, { sha: repository.commit });
      return;
    }
    if (request.method === "POST" && suffix === "/git/refs") {
      const body = await jsonBody(request);
      if (body.ref !== "refs/heads/main" || body.sha !== repository.commit) {
        send(response, 422, { message: "invalid ref" });
        return;
      }
      repository.branch = body.sha;
      send(response, 201, { ref: body.ref, object: { sha: body.sha } });
      return;
    }
    if (request.method === "PATCH" && suffix === "") {
      const body = await jsonBody(request);
      if (body.default_branch !== "main") {
        send(response, 422, { message: "invalid default branch" });
        return;
      }
      repository.defaultBranch = "main";
      send(response, 200, {
        id: repository.id,
        name: repository.name,
        full_name: fullName,
        html_url: `https://github.example.invalid/${fullName}`,
        default_branch: "main",
        description: repository.description,
        owner: { login: owner },
        private: true,
      });
      return;
    }
    if (request.method === "GET" && suffix === "/git/ref/heads/main") {
      send(response, 200, { ref: "refs/heads/main", object: { sha: repository.branch } });
      return;
    }
    if (request.method === "GET" && suffix === `/git/commits/${repository.commit}`) {
      send(response, 200, { sha: repository.commit, tree: { sha: repository.treeSha } });
      return;
    }
    if (request.method === "GET" && suffix === `/git/trees/${repository.treeSha}` && url.searchParams.get("recursive") === "1") {
      send(response, 200, {
        sha: repository.treeSha,
        truncated: false,
        tree: repository.tree.map((entry) => ({ ...entry, type: "blob" })),
      });
      return;
    }
    send(response, 404, { message: "not found" });
  } catch {
    send(response, 400, { message: "invalid request" });
  }
});

server.listen(port, "127.0.0.1");

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.once(signal, () => server.close(() => process.exit(0)));
}
