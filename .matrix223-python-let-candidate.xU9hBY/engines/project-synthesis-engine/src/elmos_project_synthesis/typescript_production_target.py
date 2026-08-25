# ruff: noqa: E501
"""TypeScript production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

Same shared contract and harness as the Python, Java and Go profiles. Token
verification uses node:crypto only -- HS256 through createHmac and RS256 through
crypto.verify with a public key imported straight from the harness JWKS -- so
the sole runtime dependency is the PostgreSQL driver, and the integration test
signs its tokens with the same stdlib the verifier uses.
"""
from __future__ import annotations

import json

from .container_images import NODE_IMAGE
from .models import FieldSpec, SynthesisRequest, pascal
from .production_contract import (
    ENV_AUTH_AUDIENCE,
    ENV_AUTH_ISSUER,
    ENV_DATABASE_URL_FILE,
    ENV_JWT_SECRET_FILE,
    ENV_OIDC_JWKS_FILE,
    ENV_OIDC_PRIVATE_KEY_FILE,
    TENANT_CLAIM,
    TENANT_SETTING,
    all_entity_sql,
    production_contract,
)
from .production_runtime import render_local_runtime
from .rendering import (
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    pretty_json,
    target_readme,
)


def _ts_type(field: FieldSpec) -> str:
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "datetime": "string",
    }[field.type]


def _sample_json(field: FieldSpec) -> object:
    return {
        "string": f"sample-{field.name}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


def _auth_ts(request: SynthesisRequest) -> str:
    if request.auth_mode == "jwt":
        key_setup = f"""
        const secret = readFileSync(mustEnv("{ENV_JWT_SECRET_FILE}"), "utf8").trim();
        if (secret.length < 32) throw new Error("JWT_SECRET_TOO_SHORT");
        const expectedAlgorithm = "HS256";
        const verifySignature = (signingInput: string, signature: Buffer): boolean => {{
          const expected = createHmac("sha256", secret).update(signingInput).digest();
          return expected.length === signature.length && timingSafeEqual(expected, signature);
        }};
        """
    else:
        key_setup = f"""
        const jwks = JSON.parse(readFileSync(mustEnv("{ENV_OIDC_JWKS_FILE}"), "utf8")) as {{
          keys: Array<Record<string, string>>;
        }};
        if (!Array.isArray(jwks.keys) || jwks.keys.length !== 1 || jwks.keys[0].kty !== "RSA") {{
          throw new Error("OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_RSA_KEY");
        }}
        const publicKey = createPublicKey({{ key: jwks.keys[0], format: "jwk" }});
        const expectedAlgorithm = "RS256";
        const verifySignature = (signingInput: string, signature: Buffer): boolean =>
          cryptoVerify("RSA-SHA256", Buffer.from(signingInput), publicKey, signature);
        """
    key_setup = clean(key_setup).rstrip().replace("\n", "\n    ")
    return clean(
        f"""
        import {{ createHmac, createPublicKey, timingSafeEqual, verify as cryptoVerify }} from "node:crypto";
        import {{ readFileSync }} from "node:fs";

        export function mustEnv(name: string): string {{
          const value = process.env[name];
          if (!value) throw new Error(`REQUIRED_ENVIRONMENT_MISSING:${{name}}`);
          return value;
        }}

        // Referenced conditionally per auth mode; keep both import sets alive.
        void createHmac;
        void createPublicKey;
        void timingSafeEqual;
        void cryptoVerify;

        interface Verifier {{
          expectedAlgorithm: string;
          verifySignature: (signingInput: string, signature: Buffer) => boolean;
          issuer: string;
          audience: string;
        }}

        let cached: Verifier | null = null;

        /**
         * Key material and issuer/audience are resolved on first use, not at
         * import time. Importing this module must stay side-effect free so the
         * offline unit test can exercise the structural rejections without a
         * provisioned secret or JWKS file.
         */
        function verifier(): Verifier {{
          if (cached !== null) return cached;
          {key_setup}
          cached = {{
            expectedAlgorithm,
            verifySignature,
            issuer: mustEnv("{ENV_AUTH_ISSUER}"),
            audience: mustEnv("{ENV_AUTH_AUDIENCE}"),
          }};
          return cached;
        }}

        function decodeSegment(segment: string): Buffer | null {{
          try {{
            return Buffer.from(segment, "base64url");
          }} catch {{
            return null;
          }}
        }}

        /**
         * Return the tenant for a verified bearer token, or null. Signature
         * validity alone never authenticates: issuer, audience, expiry and the
         * tenant claim the database policy is keyed on are all mandatory.
         */
        export function tenantFrom(authorization: string | undefined): string | null {{
          if (!authorization?.startsWith("Bearer ")) return null;
          const parts = authorization.slice("Bearer ".length).split(".");
          if (parts.length !== 3) return null;
          const headerBytes = decodeSegment(parts[0]);
          const claimBytes = decodeSegment(parts[1]);
          const signature = decodeSegment(parts[2]);
          if (!headerBytes || !claimBytes || !signature) return null;
          let header: {{ alg?: string }};
          let claims: Record<string, unknown>;
          try {{
            header = JSON.parse(headerBytes.toString("utf8"));
            claims = JSON.parse(claimBytes.toString("utf8"));
          }} catch {{
            return null;
          }}
          const {{ expectedAlgorithm, verifySignature, issuer, audience }} = verifier();
          if (header.alg !== expectedAlgorithm) return null;
          if (!verifySignature(`${{parts[0]}}.${{parts[1]}}`, signature)) return null;
          if (claims.iss !== issuer) return null;
          const aud = claims.aud;
          const audienceMatches = Array.isArray(aud) ? aud.includes(audience) : aud === audience;
          if (!audienceMatches) return null;
          const expiry = claims.exp;
          if (typeof expiry !== "number" || Date.now() / 1000 >= expiry) return null;
          const tenant = claims["{TENANT_CLAIM}"];
          if (typeof tenant !== "string" || tenant.length === 0) return null;
          return tenant;
        }}
        """
    )


def render_typescript_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    if len(request.entities) != 1:
        # Same deliberate refusal as the Go profile: emitting only the first
        # entity would silently drop declared capabilities.
        raise ValueError(
            "TYPESCRIPT_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY:"
            + ",".join(entity.singular for entity in request.entities)
        )
    entity = request.entities[0]
    entity_class = pascal(entity.singular)
    sql = all_entity_sql(request, placeholder="${}")[0]
    field_types = "\n          ".join(f"{field.name}: {_ts_type(field)};" for field in entity.fields)
    upsert_values = ", ".join(f"payload.{field.name}" for field in entity.fields)
    required_string_checks = "\n            ".join(
        f'if (typeof payload.{field.name} !== "string" || payload.{field.name}.length === 0) return null;'
        if field.type == "string" and field.required
        else f'if (typeof payload.{field.name} !== "{_ts_type(field)}") return null;'
        for field in entity.fields
    )
    allowed_keys = json.dumps(sorted(field.name for field in entity.fields))
    body_json = json.dumps({field.name: _sample_json(field) for field in entity.fields})

    files: dict[str, str] = {
        ".gitignore": gitignore() + "dist/\nnode_modules/\n",
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "production-contract.json": pretty_json(production_contract(request)),
        "package.json": pretty_json(
            {
                "name": request.project_name,
                "version": "1.0.0",
                "private": True,
                "type": "module",
                "scripts": {
                    "build": "tsc",
                    "check": "tsc --noEmit",
                    "start": "node dist/main.js",
                    # The database-backed scenario is not part of `pnpm test`;
                    # it needs a provisioned instance and runs through the
                    # runtime harness. Only the offline unit test runs here.
                    "test": "tsc && node --test dist/auth.unit.test.js",
                },
                "dependencies": {"pg": "8.16.3"},
                "devDependencies": {
                    "@types/node": "24.3.0",
                    "@types/pg": "8.15.4",
                    "typescript": "5.9.2",
                },
            }
        ),
        "tsconfig.json": pretty_json(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                    "strict": True,
                    "outDir": "dist",
                    "rootDir": "src",
                    "declaration": False,
                    "sourceMap": False,
                    "types": ["node"],
                },
                "include": ["src/**/*.ts"],
            }
        ),
        "src/auth.ts": _auth_ts(request),
        "src/store.ts": clean(
            f"""
            import {{ readFileSync }} from "node:fs";
            import pg from "pg";
            import {{ mustEnv }} from "./auth.js";

            export interface {entity_class} {{
              id: string;
              {field_types}
            }}

            export interface {entity_class}Upsert {{
              {field_types}
            }}

            const url = readFileSync(mustEnv("{ENV_DATABASE_URL_FILE}"), "utf8").trim();
            if (!url.startsWith("postgresql://")) throw new Error("DATABASE_URL_SCHEME_UNSUPPORTED");
            export const pool = new pg.Pool({{ connectionString: url, max: 8 }});

            /**
             * Run work inside one tenant-scoped transaction. {TENANT_SETTING} is
             * applied with set_config(..., true) -- transaction local -- and row
             * level security is FORCED on every table, so this binding, not the
             * SQL text, is what confines the request to its tenant.
             */
            export async function inTenant<T>(
              tenantId: string,
              work: (client: pg.PoolClient) => Promise<T>,
            ): Promise<T> {{
              if (!tenantId) throw new Error("TENANT_ID_REQUIRED");
              const client = await pool.connect();
              try {{
                await client.query("BEGIN");
                await client.query("SELECT set_config('{TENANT_SETTING}', $1, true)", [tenantId]);
                const result = await work(client);
                await client.query("COMMIT");
                return result;
              }} catch (error) {{
                await client.query("ROLLBACK");
                throw error;
              }} finally {{
                client.release();
              }}
            }}

            export function list{entity_class}s(tenantId: string): Promise<{entity_class}[]> {{
              return inTenant(tenantId, async (client) => {{
                const result = await client.query({json.dumps(sql.list_sql)});
                return result.rows as {entity_class}[];
              }});
            }}

            export function get{entity_class}(tenantId: string, recordId: string): Promise<{entity_class} | null> {{
              return inTenant(tenantId, async (client) => {{
                const result = await client.query({json.dumps(sql.get_sql)}, [recordId]);
                return (result.rows[0] as {entity_class} | undefined) ?? null;
              }});
            }}

            export function save{entity_class}(
              tenantId: string,
              recordId: string,
              payload: {entity_class}Upsert,
            ): Promise<{entity_class}> {{
              return inTenant(tenantId, async (client) => {{
                const result = await client.query({json.dumps(sql.upsert_sql)}, [
                  tenantId,
                  recordId,
                  {upsert_values},
                ]);
                return result.rows[0] as {entity_class};
              }});
            }}

            export function delete{entity_class}(tenantId: string, recordId: string): Promise<void> {{
              return inTenant(tenantId, async (client) => {{
                await client.query({json.dumps(sql.delete_sql)}, [recordId]);
              }});
            }}
            """
        ),
        "src/server.ts": clean(
            f"""
            import {{ createServer, type IncomingMessage, type Server, type ServerResponse }} from "node:http";
            import {{ tenantFrom }} from "./auth.js";
            import {{
              delete{entity_class},
              get{entity_class},
              list{entity_class}s,
              save{entity_class},
              type {entity_class}Upsert,
            }} from "./store.js";

            const UUID_PATTERN = /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/i;
            const ALLOWED_KEYS = new Set({allowed_keys} as const);

            function sendJson(response: ServerResponse, status: number, body: unknown): void {{
              response.writeHead(status, {{ "content-type": "application/json" }});
              response.end(JSON.stringify(body));
            }}

            function readBody(request: IncomingMessage): Promise<string> {{
              return new Promise((resolve, reject) => {{
                const chunks: Buffer[] = [];
                let size = 0;
                request.on("data", (chunk: Buffer) => {{
                  size += chunk.length;
                  if (size > 64 * 1024) {{
                    reject(new Error("PAYLOAD_TOO_LARGE"));
                    request.destroy();
                    return;
                  }}
                  chunks.push(chunk);
                }});
                request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
                request.on("error", reject);
              }});
            }}

            function validatedUpsert(raw: string): {entity_class}Upsert | null {{
              let payload: Record<string, unknown>;
              try {{
                payload = JSON.parse(raw);
              }} catch {{
                return null;
              }}
              if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return null;
              for (const key of Object.keys(payload)) {{
                if (!ALLOWED_KEYS.has(key as never)) return null;
              }}
              {required_string_checks}
              return payload as unknown as {entity_class}Upsert;
            }}

            export function newServer(): Server {{
              return createServer(async (request, response) => {{
                const url = new URL(request.url ?? "/", "http://localhost");
                const segments = url.pathname.split("/").filter(Boolean);
                try {{
                  if (request.method === "GET" && url.pathname === "/health") {{
                    sendJson(response, 200, {{ status: "UP", service: "{request.project_name}" }});
                    return;
                  }}
                  if (segments[0] !== "{entity.plural}" || segments.length > 2) {{
                    sendJson(response, 404, {{ error: "not_found" }});
                    return;
                  }}
                  const tenant = tenantFrom(request.headers.authorization);
                  if (!tenant) {{
                    sendJson(response, 401, {{ error: "unauthorized" }});
                    return;
                  }}
                  if (segments.length === 1) {{
                    if (request.method !== "GET") {{
                      sendJson(response, 405, {{ error: "method_not_allowed" }});
                      return;
                    }}
                    sendJson(response, 200, await list{entity_class}s(tenant));
                    return;
                  }}
                  const recordId = segments[1];
                  if (!UUID_PATTERN.test(recordId)) {{
                    sendJson(response, 422, {{ error: "RECORD_ID_MUST_BE_UUID" }});
                    return;
                  }}
                  if (request.method === "GET") {{
                    const record = await get{entity_class}(tenant, recordId);
                    if (record === null) sendJson(response, 404, {{ error: "not_found" }});
                    else sendJson(response, 200, record);
                    return;
                  }}
                  if (request.method === "PUT") {{
                    const payload = validatedUpsert(await readBody(request));
                    if (payload === null) {{
                      sendJson(response, 422, {{ error: "PAYLOAD_INVALID" }});
                      return;
                    }}
                    sendJson(response, 200, await save{entity_class}(tenant, recordId, payload));
                    return;
                  }}
                  if (request.method === "DELETE") {{
                    await delete{entity_class}(tenant, recordId);
                    response.writeHead(204);
                    response.end();
                    return;
                  }}
                  sendJson(response, 405, {{ error: "method_not_allowed" }});
                }} catch {{
                  sendJson(response, 500, {{ error: "QUERY_FAILED" }});
                }}
              }});
            }}
            """
        ),
        "src/main.ts": clean(
            f"""
            import {{ newServer }} from "./server.js";

            const port = Number.parseInt(process.env.PORT ?? "{port}", 10);
            const host = process.env.HOST ?? "0.0.0.0";
            newServer().listen(port, host, () => {{
              console.log(`listening on ${{host}}:${{port}}`);
            }});
            """
        ),
        "src/auth.unit.test.ts": clean(
            """
            import assert from "node:assert/strict";
            import { test } from "node:test";
            import { tenantFrom } from "./auth.js";

            // These rejections are decided on structure alone, before any key
            // material is needed, so they run offline. Importing ./auth.js must
            // therefore stay side-effect free.
            test("structurally invalid bearer tokens are rejected without key material", () => {
              assert.equal(tenantFrom(undefined), null);
              assert.equal(tenantFrom(""), null);
              assert.equal(tenantFrom("Basic abc"), null);
              assert.equal(tenantFrom("Bearer"), null);
              assert.equal(tenantFrom("Bearer not-a-jwt"), null);
              assert.equal(tenantFrom("Bearer only.two"), null);
              assert.equal(tenantFrom("Bearer a.b.c.d"), null);
              assert.equal(tenantFrom("Bearer !!!.!!!.!!!"), null);
            });
            """
        ),
        "src/integration.test.ts": _integration_test_ts(request, body_json),
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["sh", "-c", "pnpm install --silent && pnpm exec tsc && node dist/main.js"],
            verify_command=[
                "sh",
                "-c",
                "pnpm install --silent && pnpm exec tsc && node --test dist/integration.test.js",
            ],
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {NODE_IMAGE} AS build
            WORKDIR /workspace
            COPY package.json ./
            RUN corepack enable && pnpm install
            COPY tsconfig.json ./
            COPY src ./src
            RUN pnpm exec tsc && pnpm prune --prod

            FROM {NODE_IMAGE}
            WORKDIR /app
            COPY --from=build /workspace/dist ./dist
            COPY --from=build /workspace/node_modules ./node_modules
            USER node
            EXPOSE {port}
            ENTRYPOINT ["node", "dist/main.js"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="typescript", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: typescript-production-ci
            on:
              push:
              pull_request:
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4
                    with:
                      node-version: '26'
                  - run: corepack enable && pnpm install && pnpm exec tsc
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run build
            test:
            \tpnpm install --silent && pnpm exec tsc
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            build:
            \tpnpm exec tsc
            """
        ),
        "README.md": target_readme(
            request,
            language="TypeScript / Node",
            framework="node:http + pg",
            port=port,
            commands=(
                "pnpm install && pnpm exec tsc\n"
                "python3 scripts/local_runtime.py --verify\n"
                "python3 scripts/local_runtime.py"
            ),
        ),
    }
    return files


def _integration_test_ts(request: SynthesisRequest, body_json: str) -> str:
    entity = request.entities[0]
    if request.auth_mode == "jwt":
        signer = f"""
        function signToken(tenant: string | null, issuer: string, audience: string, valid: boolean): string {{
          const key = valid
            ? readFileSync(process.env["{ENV_JWT_SECRET_FILE}"]!, "utf8").trim()
            : "an-entirely-different-secret-value-of-length";
          const header = Buffer.from(JSON.stringify({{ alg: "HS256", typ: "JWT" }})).toString("base64url");
          const payload = Buffer.from(JSON.stringify(claims(tenant, issuer, audience))).toString("base64url");
          const signature = createHmac("sha256", key).update(`${{header}}.${{payload}}`).digest("base64url");
          return `${{header}}.${{payload}}.${{signature}}`;
        }}
        """
        signer_import = 'import { createHmac } from "node:crypto";'
    else:
        signer = f"""
        function signToken(tenant: string | null, issuer: string, audience: string, valid: boolean): string {{
          const key = valid
            ? createPrivateKey(readFileSync(process.env["{ENV_OIDC_PRIVATE_KEY_FILE}"]!))
            : generateKeyPairSync("rsa", {{ modulusLength: 2048 }}).privateKey;
          const header = Buffer.from(
            JSON.stringify({{ alg: "RS256", typ: "JWT", kid: "elmos-local-integration" }}),
          ).toString("base64url");
          const payload = Buffer.from(JSON.stringify(claims(tenant, issuer, audience))).toString("base64url");
          const signature = cryptoSign("RSA-SHA256", Buffer.from(`${{header}}.${{payload}}`), key).toString("base64url");
          return `${{header}}.${{payload}}.${{signature}}`;
        }}
        """
        signer_import = 'import { createPrivateKey, generateKeyPairSync, sign as cryptoSign } from "node:crypto";'
    signer = clean(signer).rstrip()

    return clean(
        f"""
        import assert from "node:assert/strict";
        import {{ randomUUID }} from "node:crypto";
        import {{ readFileSync }} from "node:fs";
        import {{ after, test }} from "node:test";
        {signer_import}
        import {{ newServer }} from "./server.js";
        import {{ pool }} from "./store.js";

        function claims(tenant: string | null, issuer: string, audience: string): Record<string, unknown> {{
          const body: Record<string, unknown> = {{
            iss: issuer,
            aud: audience,
            sub: "integration-subject",
            exp: Math.floor(Date.now() / 1000) + 300,
            iat: Math.floor(Date.now() / 1000),
          }};
          if (tenant) body["{TENANT_CLAIM}"] = tenant;
          return body;
        }}

        {signer}

        // The ten-step scenario from production-contract.json, against the real
        // PostgreSQL instance provisioned by scripts/local_runtime.py.
        test("shared production scenario", async () => {{
          const issuer = process.env["{ENV_AUTH_ISSUER}"];
          const audience = process.env["{ENV_AUTH_AUDIENCE}"];
          assert.ok(issuer && audience, "integration environment is not provisioned");

          const server = newServer();
          await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
          const address = server.address();
          assert.ok(address && typeof address === "object");
          const base = `http://127.0.0.1:${{address.port}}`;
          after(async () => {{
            server.close();
            await pool.end();
          }});

          const send = (method: string, path: string, bearer?: string, body?: string) =>
            fetch(base + path, {{
              method,
              headers: {{
                ...(bearer ? {{ authorization: `Bearer ${{bearer}}` }} : {{}}),
                ...(body ? {{ "content-type": "application/json" }} : {{}}),
              }},
              body,
            }});

          const tenantA = signToken("tenant-a", issuer, audience, true);
          const tenantB = signToken("tenant-b", issuer, audience, true);

          // health-unauthenticated
          assert.equal((await send("GET", "/health")).status, 200);
          // missing-token-rejected
          assert.equal((await send("GET", "/{entity.plural}")).status, 401);
          // bad-signature-rejected
          assert.equal((await send("GET", "/{entity.plural}", signToken("tenant-a", issuer, audience, false))).status, 401);
          // wrong-audience-rejected
          assert.equal((await send("GET", "/{entity.plural}", signToken("tenant-a", issuer, "another-service", true))).status, 401);
          // wrong-issuer-rejected
          assert.equal((await send("GET", "/{entity.plural}", signToken("tenant-a", "https://attacker.invalid/", audience, true))).status, 401);
          // missing-tenant-claim-rejected
          assert.equal((await send("GET", "/{entity.plural}", signToken(null, issuer, audience, true))).status, 401);

          // upsert-and-read
          const recordId = randomUUID();
          const payload = JSON.stringify({body_json});
          const created = await send("PUT", `/{entity.plural}/${{recordId}}`, tenantA, payload);
          assert.equal(created.status, 200, await created.text());
          const read = await send("GET", `/{entity.plural}/${{recordId}}`, tenantA);
          assert.equal(read.status, 200);
          assert.match(await read.text(), new RegExp(recordId));

          // list-scoped-to-tenant
          const listed = await send("GET", "/{entity.plural}", tenantA);
          assert.equal(listed.status, 200);
          assert.match(await listed.text(), new RegExp(recordId));

          // cross-tenant-read-blocked
          assert.equal((await send("GET", `/{entity.plural}/${{recordId}}`, tenantB)).status, 404);
          assert.doesNotMatch(await (await send("GET", "/{entity.plural}", tenantB)).text(), new RegExp(recordId));

          // delete-removes-record
          assert.equal((await send("DELETE", `/{entity.plural}/${{recordId}}`, tenantA)).status, 204);
          assert.equal((await send("GET", `/{entity.plural}/${{recordId}}`, tenantA)).status, 404);
        }});
        """
    )
