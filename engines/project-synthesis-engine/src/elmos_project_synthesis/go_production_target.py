# ruff: noqa: E501
"""Go production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

Same shared contract, same shared harness, same ten-step scenario as the Python
and Java profiles. Token verification is implemented with the Go standard
library (crypto/hmac, crypto/rsa) so the only third-party dependency is the
PostgreSQL driver; the integration test signs its tokens with the same stdlib,
so a verifier bug cannot be masked by a matching library quirk.
"""
from __future__ import annotations

import json

from .container_images import GOLANG_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal
from .production_contract import (
    ENV_AUTH_AUDIENCE,
    ENV_AUTH_ISSUER,
    ENV_DATABASE_URL_FILE,
    ENV_JWT_SECRET_FILE,
    ENV_OIDC_JWKS_FILE,
    ENV_OIDC_PRIVATE_KEY_FILE,
    TENANT_CLAIM,
    TENANT_SETTING,
    EntitySql,
    all_entity_sql,
    fixture_chain,
    production_contract,
    relation_parents,
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


def _go_clean(text: str) -> str:
    rendered = clean(text)
    lines: list[str] = []
    for line in rendered.splitlines():
        leading = len(line) - len(line.lstrip(" "))
        if leading:
            prefix = ("\t" * (leading // 4)) + (" " * (leading % 4))
            line = f"{prefix}{line[leading:]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _go_type(field: FieldSpec) -> str:
    return {
        "string": "string",
        "integer": "int64",
        "number": "float64",
        "boolean": "bool",
        "datetime": "time.Time",
    }[field.type]


def _sample_json(field: FieldSpec) -> object:
    return {
        "string": f"sample-{field.name}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


def _go_json_body(request: SynthesisRequest, entity: EntitySpec, parent_vars: dict[str, str]) -> str:
    parents = dict(relation_parents(request, entity.singular))
    fragments: list[str] = []
    sprintf_args: list[str] = []
    for field in entity.fields:
        if field.name in parents:
            fragments.append(f'"{field.name}":%q')
            sprintf_args.append(parent_vars[parents[field.name]])
        else:
            fragments.append(f'"{field.name}":{json.dumps(_sample_json(field))}')
    template = "{" + ",".join(fragments) + "}"
    if not sprintf_args:
        return "`" + template + "`"
    return "fmt.Sprintf(`" + template + "`, " + ", ".join(sprintf_args) + ")"


def _go_entity_store_block(entity: EntitySpec, sql: EntitySql) -> str:
    entity_class = pascal(entity.singular)
    list_name = f"list{pascal(entity.plural)}"
    field_declarations = "\n    ".join(
        f'{pascal(field.name)} {_go_type(field)} `json:"{field.name}"`' for field in entity.fields
    )
    scan_targets = ", ".join(["&record.ID", *(f"&record.{pascal(field.name)}" for field in entity.fields)])
    upsert_arguments = ", ".join(
        ["tenantID", "recordID", *(f"payload.{pascal(field.name)}" for field in entity.fields)]
    )
    return f"""
            type {entity_class} struct {{
                ID string `json:"id"`
                {field_declarations}
            }}

            type {entity_class}Upsert struct {{
                {field_declarations}
            }}

            func (s *store) {list_name}(ctx context.Context, tenantID string) ([]{entity_class}, error) {{
                results := []{entity_class}{{}}
                err := s.inTenant(ctx, tenantID, func(transaction *sql.Tx) error {{
                    rows, err := transaction.QueryContext(ctx, {json.dumps(sql.list_sql)})
                    if err != nil {{
                        return err
                    }}
                    defer rows.Close()
                    for rows.Next() {{
                        var record {entity_class}
                        if err := rows.Scan({scan_targets}); err != nil {{
                            return err
                        }}
                        results = append(results, record)
                    }}
                    return rows.Err()
                }})
                return results, err
            }}

            func (s *store) get{entity_class}(ctx context.Context, tenantID, recordID string) (*{entity_class}, error) {{
                var found *{entity_class}
                err := s.inTenant(ctx, tenantID, func(transaction *sql.Tx) error {{
                    var record {entity_class}
                    row := transaction.QueryRowContext(ctx, {json.dumps(sql.get_sql)}, recordID)
                    if err := row.Scan({scan_targets}); err != nil {{
                        if errors.Is(err, sql.ErrNoRows) {{
                            return nil
                        }}
                        return err
                    }}
                    found = &record
                    return nil
                }})
                return found, err
            }}

            func (s *store) save{entity_class}(ctx context.Context, tenantID, recordID string, payload {entity_class}Upsert) (*{entity_class}, error) {{
                var saved *{entity_class}
                err := s.inTenant(ctx, tenantID, func(transaction *sql.Tx) error {{
                    var record {entity_class}
                    row := transaction.QueryRowContext(ctx, {json.dumps(sql.upsert_sql)}, {upsert_arguments})
                    if err := row.Scan({scan_targets}); err != nil {{
                        return err
                    }}
                    saved = &record
                    return nil
                }})
                return saved, err
            }}

            func (s *store) delete{entity_class}(ctx context.Context, tenantID, recordID string) error {{
                return s.inTenant(ctx, tenantID, func(transaction *sql.Tx) error {{
                    _, err := transaction.ExecContext(ctx, {json.dumps(sql.delete_sql)}, recordID)
                    return err
                }})
            }}
            """


def _go_entity_handler_block(entity: EntitySpec) -> str:
    entity_class = pascal(entity.singular)
    list_name = f"list{pascal(entity.plural)}"
    return f"""
                mux.HandleFunc("GET /{entity.plural}", func(response http.ResponseWriter, request *http.Request) {{
                    tenant, ok := requireTenant(response, request)
                    if !ok {{
                        return
                    }}
                    results, err := records.{list_name}(request.Context(), tenant)
                    if err != nil {{
                        writeJSON(response, http.StatusInternalServerError, map[string]string{{"error": "QUERY_FAILED"}})
                        return
                    }}
                    writeJSON(response, http.StatusOK, results)
                }})
                mux.HandleFunc("GET /{entity.plural}/{{id}}", func(response http.ResponseWriter, request *http.Request) {{
                    tenant, ok := requireTenant(response, request)
                    if !ok {{
                        return
                    }}
                    recordID, ok := requireRecordID(response, request)
                    if !ok {{
                        return
                    }}
                    record, err := records.get{entity_class}(request.Context(), tenant, recordID)
                    if err != nil {{
                        writeJSON(response, http.StatusInternalServerError, map[string]string{{"error": "QUERY_FAILED"}})
                        return
                    }}
                    if record == nil {{
                        writeJSON(response, http.StatusNotFound, map[string]string{{"error": "not_found"}})
                        return
                    }}
                    writeJSON(response, http.StatusOK, record)
                }})
                mux.HandleFunc("PUT /{entity.plural}/{{id}}", func(response http.ResponseWriter, request *http.Request) {{
                    tenant, ok := requireTenant(response, request)
                    if !ok {{
                        return
                    }}
                    recordID, ok := requireRecordID(response, request)
                    if !ok {{
                        return
                    }}
                    payload, ok := validated{entity_class}Upsert(request)
                    if !ok {{
                        writeJSON(response, http.StatusUnprocessableEntity, map[string]string{{"error": "PAYLOAD_INVALID"}})
                        return
                    }}
                    record, err := records.save{entity_class}(request.Context(), tenant, recordID, *payload)
                    if err != nil {{
                        writeJSON(response, http.StatusInternalServerError, map[string]string{{"error": "QUERY_FAILED"}})
                        return
                    }}
                    writeJSON(response, http.StatusOK, record)
                }})
                mux.HandleFunc("DELETE /{entity.plural}/{{id}}", func(response http.ResponseWriter, request *http.Request) {{
                    tenant, ok := requireTenant(response, request)
                    if !ok {{
                        return
                    }}
                    recordID, ok := requireRecordID(response, request)
                    if !ok {{
                        return
                    }}
                    if err := records.delete{entity_class}(request.Context(), tenant, recordID); err != nil {{
                        writeJSON(response, http.StatusInternalServerError, map[string]string{{"error": "QUERY_FAILED"}})
                        return
                    }}
                    response.WriteHeader(http.StatusNoContent)
                }})
            """


def _go_validator_funcs(request: SynthesisRequest) -> str:
    blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        required_checks = "\n    ".join(
            f'if payload.{pascal(field.name)} == "" {{\n        return nil, false\n    }}'
            for field in entity.fields
            if field.required and field.type == "string"
        ) or "_ = payload"
        blocks.append(
            f"""
            func validated{entity_class}Upsert(request *http.Request) (*{entity_class}Upsert, bool) {{
                var payload {entity_class}Upsert
                decoder := json.NewDecoder(request.Body)
                decoder.DisallowUnknownFields()
                if decoder.Decode(&payload) != nil {{
                    return nil, false
                }}
                {required_checks}
                return &payload, true
            }}
            """
        )
    return "\n".join(blocks)


def _go_entity_scenario(
    request: SynthesisRequest,
    entity: EntitySpec,
    declared_vars: set[str] | None = None,
) -> str:
    if declared_vars is None:
        declared_vars = set()
    by_name = {item.singular: item for item in request.entities}
    parent_vars: dict[str, str] = {}
    lines: list[str] = []
    for parent in fixture_chain(request, entity.singular):
        variable = f"{parent}ID"
        parent_vars[parent] = variable
        parent_entity = by_name[parent]
        body = _go_json_body(request, parent_entity, parent_vars)
        assign_op = "=" if variable in declared_vars else ":="
        declared_vars.add(variable)
        lines.extend(
            [
                f"{variable} {assign_op} uuidString(test)",
                f"response, body = send(test, server, \"PUT\", \"/{parent_entity.plural}/\"+{variable}, tenantA, {body})",
                f"expectStatus(test, \"fixture {parent}\", response, 200, body)",
            ]
        )
    record_var = f"{entity.singular}ID"
    body = _go_json_body(request, entity, parent_vars)
    assign_op = "=" if record_var in declared_vars else ":="
    declared_vars.add(record_var)
    lines.extend(
        [
            f"{record_var} {assign_op} uuidString(test)",
            f"response, body = send(test, server, \"PUT\", \"/{entity.plural}/\"+{record_var}, tenantA, {body})",
            f'expectStatus(test, "upsert-and-read {entity.singular} (PUT)", response, 200, body)',
            f"response, body = send(test, server, \"GET\", \"/{entity.plural}/\"+{record_var}, tenantA, \"\")",
            f'expectStatus(test, "upsert-and-read {entity.singular} (GET)", response, 200, body)',
            f"if !strings.Contains(body, {record_var}) {{\n"
            f'                test.Fatalf("upsert-and-read {entity.singular}: record id missing from body %s", body)\n'
            f"            }}",
            f"response, body = send(test, server, \"GET\", \"/{entity.plural}\", tenantA, \"\")",
            f'expectStatus(test, "list-scoped-to-tenant {entity.singular}", response, 200, body)',
            f"if !strings.Contains(body, {record_var}) {{\n"
            f'                test.Fatalf("list-scoped-to-tenant {entity.singular}: record id missing from %s", body)\n'
            f"            }}",
            f"response, body = send(test, server, \"GET\", \"/{entity.plural}/\"+{record_var}, tenantB, \"\")",
            f'expectStatus(test, "cross-tenant-read-blocked {entity.singular}", response, 404, body)',
            f"response, body = send(test, server, \"GET\", \"/{entity.plural}\", tenantB, \"\")",
            f'expectStatus(test, "cross-tenant-read-blocked {entity.singular} (list)", response, 200, body)',
            f"if strings.Contains(body, {record_var}) {{\n"
            f'                test.Fatalf("cross-tenant-read-blocked {entity.singular}: tenant-b can see %s", {record_var})\n'
            f"            }}",
            f"response, body = send(test, server, \"DELETE\", fmt.Sprintf(\"/{entity.plural}/%s\", {record_var}), tenantA, \"\")",
            f'expectStatus(test, "delete-removes-record {entity.singular}", response, 204, body)',
            f"response, body = send(test, server, \"GET\", \"/{entity.plural}/\"+{record_var}, tenantA, \"\")",
            f'expectStatus(test, "delete-removes-record {entity.singular} (GET)", response, 404, body)',
        ]
    )
    return "\n            ".join(lines)


def _auth_go(request: SynthesisRequest) -> str:
    """The bearer verifier. Issuer, audience, expiry and tenant claim are all
    mandatory; a structurally valid signature alone never authenticates."""
    if request.auth_mode == "jwt":
        key_setup = f"""
        secretPath := mustEnv("{ENV_JWT_SECRET_FILE}")
        raw, err := os.ReadFile(secretPath)
        if err != nil {{
            log.Fatalf("JWT_SECRET_UNREADABLE: %v", err)
        }}
        secret := []byte(strings.TrimSpace(string(raw)))
        if len(secret) < 32 {{
            log.Fatal("JWT_SECRET_TOO_SHORT")
        }}
        verify := func(signingInput, signature []byte) bool {{
            mac := hmac.New(sha256.New, secret)
            mac.Write(signingInput)
            return hmac.Equal(mac.Sum(nil), signature)
        }}
        expectedAlgorithm := "HS256"
        """
    else:
        key_setup = f"""
        jwksPath := mustEnv("{ENV_OIDC_JWKS_FILE}")
        raw, err := os.ReadFile(jwksPath)
        if err != nil {{
            log.Fatalf("OIDC_JWKS_UNREADABLE: %v", err)
        }}
        var jwks struct {{
            Keys []struct {{
                Kty string `json:"kty"`
                N   string `json:"n"`
                E   string `json:"e"`
            }} `json:"keys"`
        }}
        if err := json.Unmarshal(raw, &jwks); err != nil || len(jwks.Keys) != 1 || jwks.Keys[0].Kty != "RSA" {{
            log.Fatal("OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_RSA_KEY")
        }}
        nBytes, err := base64.RawURLEncoding.DecodeString(jwks.Keys[0].N)
        if err != nil {{
            log.Fatalf("OIDC_JWKS_MODULUS_INVALID: %v", err)
        }}
        eBytes, err := base64.RawURLEncoding.DecodeString(jwks.Keys[0].E)
        if err != nil {{
            log.Fatalf("OIDC_JWKS_EXPONENT_INVALID: %v", err)
        }}
        publicKey := &rsa.PublicKey{{N: new(big.Int).SetBytes(nBytes), E: int(new(big.Int).SetBytes(eBytes).Int64())}}
        verify := func(signingInput, signature []byte) bool {{
            digest := sha256.Sum256(signingInput)
            return rsa.VerifyPKCS1v15(publicKey, crypto.SHA256, digest[:], signature) == nil
        }}
        expectedAlgorithm := "RS256"
        """
    key_setup = clean(key_setup).rstrip().replace("\n", "\n    ")
    return _go_clean(
        f"""
        package main

        import (
            "crypto"
            "crypto/hmac"
            "crypto/rsa"
            "crypto/sha256"
            "encoding/base64"
            "encoding/json"
            "log"
            "math/big"
            "os"
            "strings"
            "time"
        )

        // Unused imports are compile errors in Go, and the two auth modes need
        // different subsets, so silence the mode that is not compiled in.
        var _ = crypto.SHA256
        var _ = rsa.ErrVerification
        var _ = hmac.New
        var _ = big.NewInt

        type authenticator struct {{
            issuer   string
            audience string
            verify   func(signingInput, signature []byte) bool
            algorithm string
        }}

        func mustEnv(name string) string {{
            value := os.Getenv(name)
            if value == "" {{
                log.Fatalf("REQUIRED_ENVIRONMENT_MISSING:%s", name)
            }}
            return value
        }}

        func newAuthenticator() *authenticator {{
            {key_setup}
            return &authenticator{{
                issuer:    mustEnv("{ENV_AUTH_ISSUER}"),
                audience:  mustEnv("{ENV_AUTH_AUDIENCE}"),
                verify:    verify,
                algorithm: expectedAlgorithm,
            }}
        }}

        // tenantFrom returns the tenant for a verified bearer token, or "".
        // Every rejection path is deliberate: wrong algorithm, bad signature,
        // wrong issuer, wrong audience, missing tenant claim and expiry all
        // fail closed rather than falling through to a database query.
        func (a *authenticator) tenantFrom(authorization string) string {{
            token, found := strings.CutPrefix(authorization, "Bearer ")
            if !found {{
                return ""
            }}
            parts := strings.Split(token, ".")
            if len(parts) != 3 {{
                return ""
            }}
            headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
            if err != nil {{
                return ""
            }}
            var header struct {{
                Algorithm string `json:"alg"`
            }}
            if json.Unmarshal(headerBytes, &header) != nil || header.Algorithm != a.algorithm {{
                return ""
            }}
            signature, err := base64.RawURLEncoding.DecodeString(parts[2])
            if err != nil {{
                return ""
            }}
            if !a.verify([]byte(parts[0]+"."+parts[1]), signature) {{
                return ""
            }}
            claimBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
            if err != nil {{
                return ""
            }}
            var claims struct {{
                Issuer   string          `json:"iss"`
                Audience json.RawMessage `json:"aud"`
                Tenant   string          `json:"{TENANT_CLAIM}"`
                Expiry   int64           `json:"exp"`
            }}
            if json.Unmarshal(claimBytes, &claims) != nil {{
                return ""
            }}
            if claims.Issuer != a.issuer || !audienceMatches(claims.Audience, a.audience) {{
                return ""
            }}
            if claims.Tenant == "" || claims.Expiry == 0 || time.Now().Unix() >= claims.Expiry {{
                return ""
            }}
            return claims.Tenant
        }}

        func audienceMatches(raw json.RawMessage, expected string) bool {{
            var single string
            if json.Unmarshal(raw, &single) == nil {{
                return single == expected
            }}
            var many []string
            if json.Unmarshal(raw, &many) == nil {{
                for _, candidate := range many {{
                    if candidate == expected {{
                        return true
                    }}
                }}
            }}
            return false
        }}
        """
    )


def render_go_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    module = request.project_name
    statements = {item.entity: item for item in all_entity_sql(request, placeholder="${}")}
    needs_time = any(
        field.type == "datetime" for entity in request.entities for field in entity.fields
    )
    time_import = '\n            "time"' if needs_time else ""
    entity_store_blocks = "\n".join(
        _go_entity_store_block(entity, statements[entity.singular]) for entity in request.entities
    )
    entity_handler_blocks = "\n".join(_go_entity_handler_block(entity) for entity in request.entities)
    validator_funcs = _go_validator_funcs(request)

    files: dict[str, str] = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "production-contract.json": pretty_json(production_contract(request)),
        "go.mod": clean(
            f"""
            module {module}

            go 1.25.0

            require github.com/lib/pq v1.10.9
            """
        ),
        # Shipped rather than generated: `go vet` and `go build` run before any
        # tidy step, so a workspace without go.sum fails verification on a
        # missing entry instead of on anything about the generated code.
        "go.sum": clean(
            """
            github.com/lib/pq v1.10.9 h1:YXG7RB+JIjhP29X+OtkiDnYaXQwpS4JEWq7dtCCRUEw=
            github.com/lib/pq v1.10.9/go.mod h1:AlVN5x4E4T544tWzH6hKfbfQvm3HdbOxrmggDNAPY9o=
            """
        ),
        "auth.go": _auth_go(request),
        "store.go": _go_clean(
            f"""
            package main

            import (
                "context"
                "database/sql"
                "errors"{time_import}
            )

            type store struct {{
                database *sql.DB
            }}

            // inTenant runs work inside one transaction whose {TENANT_SETTING}
            // is set with set_config(..., true), i.e. transaction-local. Row
            // level security is FORCED on every table, so this binding -- not
            // any SQL predicate -- is what confines the request to its tenant.
            func (s *store) inTenant(ctx context.Context, tenantID string, work func(*sql.Tx) error) error {{
                if tenantID == "" {{
                    return errors.New("TENANT_ID_REQUIRED")
                }}
                transaction, err := s.database.BeginTx(ctx, nil)
                if err != nil {{
                    return err
                }}
                if _, err := transaction.ExecContext(ctx, "SELECT set_config('{TENANT_SETTING}', $1, true)", tenantID); err != nil {{
                    _ = transaction.Rollback()
                    return err
                }}
                if err := work(transaction); err != nil {{
                    _ = transaction.Rollback()
                    return err
                }}
                return transaction.Commit()
            }}

            {entity_store_blocks}
            """
        ),
        "main.go": _go_clean(
            f"""
            package main

            import (
                "database/sql"
                "encoding/json"
                "log"
                "net/http"
                "os"
                "regexp"
                "strings"

                _ "github.com/lib/pq"
            )

            var identifierPattern = regexp.MustCompile(`^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}$`)

            func openDatabase() *sql.DB {{
                reference := mustEnv("{ENV_DATABASE_URL_FILE}")
                raw, err := os.ReadFile(reference)
                if err != nil {{
                    log.Fatalf("DATABASE_URL_UNREADABLE: %v", err)
                }}
                url := strings.TrimSpace(string(raw))
                if !strings.HasPrefix(url, "postgresql://") {{
                    log.Fatal("DATABASE_URL_SCHEME_UNSUPPORTED")
                }}
                database, err := sql.Open("postgres", url)
                if err != nil {{
                    log.Fatalf("DATABASE_OPEN_FAILED: %v", err)
                }}
                if err := database.Ping(); err != nil {{
                    log.Fatalf("DATABASE_UNREACHABLE: %v", err)
                }}
                return database
            }}

            func writeJSON(response http.ResponseWriter, status int, body any) {{
                response.Header().Set("Content-Type", "application/json")
                response.WriteHeader(status)
                _ = json.NewEncoder(response).Encode(body)
            }}

            {validator_funcs}

            func newHandler(auth *authenticator, records *store) http.Handler {{
                mux := http.NewServeMux()
                mux.HandleFunc("GET /health", func(response http.ResponseWriter, request *http.Request) {{
                    writeJSON(response, http.StatusOK, map[string]string{{"status": "UP", "service": "{request.project_name}"}})
                }})
                requireTenant := func(response http.ResponseWriter, request *http.Request) (string, bool) {{
                    tenant := auth.tenantFrom(request.Header.Get("Authorization"))
                    if tenant == "" {{
                        writeJSON(response, http.StatusUnauthorized, map[string]string{{"error": "unauthorized"}})
                        return "", false
                    }}
                    return tenant, true
                }}
                requireRecordID := func(response http.ResponseWriter, request *http.Request) (string, bool) {{
                    recordID := request.PathValue("id")
                    if !identifierPattern.MatchString(recordID) {{
                        writeJSON(response, http.StatusUnprocessableEntity, map[string]string{{"error": "RECORD_ID_MUST_BE_UUID"}})
                        return "", false
                    }}
                    return recordID, true
                }}
                {entity_handler_blocks}
                return mux
            }}

            func main() {{
                port := os.Getenv("PORT")
                if port == "" {{
                    port = "{port}"
                }}
                host := os.Getenv("HOST")
                if host == "" {{
                    host = "0.0.0.0"
                }}
                database := openDatabase()
                defer database.Close()
                handler := newHandler(newAuthenticator(), &store{{database: database}})
                log.Printf("listening on %s:%s", host, port)
                log.Fatal(http.ListenAndServe(host+":"+port, handler))
            }}
            """
        ),
        "integration_test.go": _integration_test_go(request),
        # `go mod tidy` runs first so the module sum is materialized before the
        # build; without it a fresh workspace fails on missing go.sum entries.
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["go", "run", "."],
            verify_command=["go", "test", "-tags", "integration", "-count=1", "./..."],
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {GOLANG_IMAGE} AS build
            WORKDIR /workspace
            COPY go.mod go.sum ./
            RUN go mod download
            COPY . .
            RUN CGO_ENABLED=0 go build -o /out/service .

            FROM scratch
            COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
            COPY --from=build /out/service /service
            EXPOSE {port}
            USER 10001:10001
            ENTRYPOINT ["/service"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="go", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: go-production-ci
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
                  - uses: actions/setup-go@d35c59abb061a4a6fb18e82ac0862c26744d6ab5 # v5
                    with:
                      go-version: '1.25.0'
                  - run: go vet ./...
                  - run: go test ./...
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run build
            test:
            \tgo vet ./... && go test ./...
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            build:
            \tgo build -o bin/service .
            """
        ),
        "README.md": target_readme(
            request,
            language="Go 1.25.0",
            framework="net/http + database/sql",
            port=port,
            commands=(
                "go vet ./... && go test ./...\n"
                "python3 scripts/local_runtime.py --verify\n"
                "python3 scripts/local_runtime.py"
            ),
        ),
    }
    return files


def _integration_test_go(request: SynthesisRequest) -> str:
    entity = request.entities[0]
    declared_vars: set[str] = set()
    entity_scenarios = "\n            ".join(
        _go_entity_scenario(request, item, declared_vars) for item in request.entities
    )
    if request.auth_mode == "jwt":
        signer = f"""
        func signToken(test *testing.T, tenant, issuer, audience string, valid bool) string {{
            test.Helper()
            secret, err := os.ReadFile(os.Getenv("{ENV_JWT_SECRET_FILE}"))
            if err != nil {{
                test.Fatalf("secret unreadable: %v", err)
            }}
            key := bytes.TrimSpace(secret)
            if !valid {{
                key = []byte("an-entirely-different-secret-value-of-length")
            }}
            header := base64.RawURLEncoding.EncodeToString([]byte(`{{"alg":"HS256","typ":"JWT"}}`))
            payload := base64.RawURLEncoding.EncodeToString(claimsJSON(tenant, issuer, audience))
            mac := hmac.New(sha256.New, key)
            mac.Write([]byte(header + "." + payload))
            return header + "." + payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
        }}
        """
        signer_imports = '"bytes"\n            "crypto/hmac"\n            "crypto/rand"'
    else:
        signer = f"""
        func signToken(test *testing.T, tenant, issuer, audience string, valid bool) string {{
            test.Helper()
            var key *rsa.PrivateKey
            if valid {{
                pemBytes, err := os.ReadFile(os.Getenv("{ENV_OIDC_PRIVATE_KEY_FILE}"))
                if err != nil {{
                    test.Fatalf("private key unreadable: %v", err)
                }}
                block, _ := pem.Decode(pemBytes)
                if block == nil {{
                    test.Fatal("private key PEM invalid")
                }}
                parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
                if err != nil {{
                    test.Fatalf("private key parse failed: %v", err)
                }}
                key = parsed.(*rsa.PrivateKey)
            }} else {{
                generated, err := rsa.GenerateKey(rand.Reader, 2048)
                if err != nil {{
                    test.Fatalf("wrong-key generation failed: %v", err)
                }}
                key = generated
            }}
            header := base64.RawURLEncoding.EncodeToString([]byte(`{{"alg":"RS256","typ":"JWT","kid":"elmos-local-integration"}}`))
            payload := base64.RawURLEncoding.EncodeToString(claimsJSON(tenant, issuer, audience))
            digest := sha256.Sum256([]byte(header + "." + payload))
            signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
            if err != nil {{
                test.Fatalf("signing failed: %v", err)
            }}
            return header + "." + payload + "." + base64.RawURLEncoding.EncodeToString(signature)
        }}
        """
        signer_imports = '"crypto"\n            "crypto/rand"\n            "crypto/rsa"\n            "crypto/x509"\n            "encoding/pem"'
    # Re-indent to the template's body depth so textwrap.dedent still finds a
    # uniform prefix across the whole emitted file.
    signer = clean(signer).rstrip().replace("\n", "\n        ")

    return _go_clean(
        f"""
        //go:build integration

        package main

        import (
            {signer_imports}
            "crypto/sha256"
            "encoding/base64"
            "encoding/json"
            "fmt"
            "io"
            "net/http"
            "net/http/httptest"
            "os"
            "strings"
            "testing"
            "time"
        )

        // uuidString mints a v4 UUID with the standard library so the test
        // suite adds no dependency beyond the database driver.
        func uuidString(test *testing.T) string {{
            test.Helper()
            var raw [16]byte
            if _, err := rand.Read(raw[:]); err != nil {{
                test.Fatalf("uuid entropy unavailable: %v", err)
            }}
            raw[6] = (raw[6] & 0x0f) | 0x40
            raw[8] = (raw[8] & 0x3f) | 0x80
            return fmt.Sprintf("%x-%x-%x-%x-%x", raw[0:4], raw[4:6], raw[6:8], raw[8:10], raw[10:16])
        }}

        func claimsJSON(tenant, issuer, audience string) []byte {{
            claims := map[string]any{{
                "iss": issuer,
                "aud": audience,
                "sub": "integration-subject",
                "exp": time.Now().Add(5 * time.Minute).Unix(),
                "iat": time.Now().Unix(),
            }}
            if tenant != "" {{
                claims["{TENANT_CLAIM}"] = tenant
            }}
            encoded, _ := json.Marshal(claims)
            return encoded
        }}

        {signer}

        func send(test *testing.T, server *httptest.Server, method, path, bearer, body string) (*http.Response, string) {{
            test.Helper()
            var reader io.Reader
            if body != "" {{
                reader = strings.NewReader(body)
            }}
            request, err := http.NewRequest(method, server.URL+path, reader)
            if err != nil {{
                test.Fatalf("request build failed: %v", err)
            }}
            if bearer != "" {{
                request.Header.Set("Authorization", "Bearer "+bearer)
            }}
            if body != "" {{
                request.Header.Set("Content-Type", "application/json")
            }}
            response, err := server.Client().Do(request)
            if err != nil {{
                test.Fatalf("request failed: %v", err)
            }}
            defer response.Body.Close()
            content, _ := io.ReadAll(response.Body)
            return response, string(content)
        }}

        func expectStatus(test *testing.T, step string, got *http.Response, want int, body string) {{
            test.Helper()
            if got.StatusCode != want {{
                test.Fatalf("%s: expected %d got %d body=%s", step, want, got.StatusCode, body)
            }}
        }}

        // TestSharedProductionScenario executes the ten-step scenario from
        // production-contract.json against the real PostgreSQL instance the
        // harness provisioned. Every step id below matches the contract.
        func TestSharedProductionScenario(test *testing.T) {{
            issuer := os.Getenv("{ENV_AUTH_ISSUER}")
            audience := os.Getenv("{ENV_AUTH_AUDIENCE}")
            if issuer == "" || audience == "" {{
                test.Fatal("integration environment is not provisioned; run through scripts/local_runtime.py --verify")
            }}
            database := openDatabase()
            defer database.Close()
            server := httptest.NewServer(newHandler(newAuthenticator(), &store{{database: database}}))
            defer server.Close()

            tenantA := signToken(test, "tenant-a", issuer, audience, true)
            tenantB := signToken(test, "tenant-b", issuer, audience, true)

            // health-unauthenticated
            response, body := send(test, server, "GET", "/health", "", "")
            expectStatus(test, "health-unauthenticated", response, 200, body)

            // missing-token-rejected
            response, body = send(test, server, "GET", "/{entity.plural}", "", "")
            expectStatus(test, "missing-token-rejected", response, 401, body)

            // bad-signature-rejected
            response, body = send(test, server, "GET", "/{entity.plural}", signToken(test, "tenant-a", issuer, audience, false), "")
            expectStatus(test, "bad-signature-rejected", response, 401, body)

            // wrong-audience-rejected
            response, body = send(test, server, "GET", "/{entity.plural}", signToken(test, "tenant-a", issuer, "another-service", true), "")
            expectStatus(test, "wrong-audience-rejected", response, 401, body)

            // wrong-issuer-rejected
            response, body = send(test, server, "GET", "/{entity.plural}", signToken(test, "tenant-a", "https://attacker.invalid/", audience, true), "")
            expectStatus(test, "wrong-issuer-rejected", response, 401, body)

            // missing-tenant-claim-rejected
            response, body = send(test, server, "GET", "/{entity.plural}", signToken(test, "", issuer, audience, true), "")
            expectStatus(test, "missing-tenant-claim-rejected", response, 401, body)

            {entity_scenarios}
        }}
        """
    )
