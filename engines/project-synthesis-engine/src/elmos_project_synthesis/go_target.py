# ruff: noqa: E501

from __future__ import annotations

import json
from textwrap import indent

from .container_images import GOLANG_IMAGE
from .models import FieldSpec, SynthesisRequest, pascal
from .rendering import (
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    sample_payload,
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
    base = {
        "string": "string",
        "integer": "int64",
        "number": "float64",
        "boolean": "bool",
        "datetime": "time.Time",
    }[field.type]
    return base if field.required else f"*{base}"


def render_go(request: SynthesisRequest, port: int) -> dict[str, str]:
    model_blocks: list[str] = []
    store_blocks: list[str] = []
    route_blocks: list[str] = []
    test_blocks: list[str] = []
    needs_time = False
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        needs_time = needs_time or any(field.type == "datetime" for field in entity.fields)
        model_lines = [f"type {entity_class}Upsert struct {{"]
        for index, field in enumerate(entity.fields):
            if index:
                model_lines.append("")
            model_lines.append(f'\t{pascal(field.name)} {_go_type(field)} `json:"{field.name}"`')
        model_lines.extend(
            [
                "}",
                "",
                f"type {entity_class} struct {{",
                '\tID string `json:"id"`',
                "",
                f"\t{entity_class}Upsert",
                "}",
            ]
        )
        model_blocks.append("\n".join(model_lines))
        store_name = f"{entity.plural}Store"
        store_blocks.append(f"var {store_name} = newStore[{entity_class}Upsert]()")
        route_blocks.append(f'registerResource(mux, "/api/v1/{entity.plural}", {store_name})')
        sample = json.dumps(sample_payload(request, entity), ensure_ascii=False, separators=(",", ":"))
        test_blocks.append(
            _go_clean(
                f"""
                func Test{entity_class}FullCRUD(t *testing.T) {{
                    server := httptest.NewServer(newHandler())
                    defer server.Close()
                    payload := []byte(`{sample}`)
                    created := request(t, http.MethodPost, server.URL+"/api/v1/{entity.plural}", payload)
                    if created.Code != http.StatusCreated {{
                        t.Fatalf("create status = %d: %s", created.Code, created.Body.String())
                    }}
                    var record map[string]any
                    decodeJSON(t, created.Body.Bytes(), &record)
                    id := record["id"].(string)
                    if got := request(t, http.MethodGet, server.URL+"/api/v1/{entity.plural}/"+id, nil); got.Code != http.StatusOK {{
                        t.Fatalf("get status = %d", got.Code)
                    }}
                    if got := request(t, http.MethodPut, server.URL+"/api/v1/{entity.plural}/"+id, payload); got.Code != http.StatusOK {{
                        t.Fatalf("update status = %d", got.Code)
                    }}
                    if got := request(t, http.MethodDelete, server.URL+"/api/v1/{entity.plural}/"+id, nil); got.Code != http.StatusNoContent {{
                        t.Fatalf("delete status = %d", got.Code)
                    }}
                    if got := request(t, http.MethodGet, server.URL+"/api/v1/{entity.plural}/"+id, nil); got.Code != http.StatusNotFound {{
                        t.Fatalf("missing status = %d", got.Code)
                    }}
                }}
                """
            ).rstrip()
        )
    time_import = '\n                "time"' if needs_time else ""
    models = "\n\n".join(model_blocks)
    stores = "\n".join(store_blocks)
    routes = "\n".join(route_blocks)
    tests = "\n\n".join(test_blocks)
    indented_models = indent(models, "            ")
    indented_stores = indent(stores, "            ")
    indented_routes = indent(routes, "                ")
    indented_tests = indent(tests, "            ")
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "go.mod": clean(
            f"""
            module {request.namespace.replace(".", "/")}/{request.project_name}

            go 1.25.0
            """
        ),
        "models.go": _go_clean(
            f"""
            package main

            import (
                "encoding/json"
                "sync"{time_import}
            )

{indented_models}

            type store[T any] struct {{
                mutex sync.RWMutex

                records map[string]json.RawMessage
            }}

            func newStore[T any]() *store[T] {{
                return &store[T]{{records: make(map[string]json.RawMessage)}}
            }}
            """
        ),
        "main.go": _go_clean(
            f"""
            package main

            import (
                "crypto/rand"
                "encoding/hex"
                "encoding/json"
                "errors"
                "io"
                "log/slog"
                "net/http"
                "os"
                "sort"
                "strings"
            )

{indented_stores}

            func identifier() string {{
                value := make([]byte, 16)
                if _, err := rand.Read(value); err != nil {{
                    panic(err)
                }}
                return hex.EncodeToString(value)
            }}

            func writeJSON(writer http.ResponseWriter, status int, value any) {{
                writer.Header().Set("Content-Type", "application/json")
                writer.WriteHeader(status)
                if status != http.StatusNoContent {{
                    _ = json.NewEncoder(writer).Encode(value)
                }}
            }}

            func decode[T any](request *http.Request) (T, error) {{
                var value T
                decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
                decoder.DisallowUnknownFields()
                if err := decoder.Decode(&value); err != nil {{
                    return value, err
                }}
                return value, nil
            }}

            func registerResource[T any](mux *http.ServeMux, collection string, data *store[T]) {{
                mux.HandleFunc(collection, func(writer http.ResponseWriter, request *http.Request) {{
                    switch request.Method {{
                    case http.MethodGet:
                        data.mutex.RLock()
                        defer data.mutex.RUnlock()
                        ids := make([]string, 0, len(data.records))
                        for id := range data.records {{
                            ids = append(ids, id)
                        }}
                        sort.Strings(ids)
                        records := make([]json.RawMessage, 0, len(ids))
                        for _, id := range ids {{
                            records = append(records, data.records[id])
                        }}
                        writeJSON(writer, http.StatusOK, records)
                    case http.MethodPost:
                        payload, err := decode[T](request)
                        if err != nil {{
                            writeJSON(writer, http.StatusBadRequest, map[string]string{{"error": err.Error()}})
                            return
                        }}
                        id := identifier()
                        object, _ := json.Marshal(struct {{
                            ID string `json:"id"`

                            Payload T `json:",inline"`
                        }}{{ID: id, Payload: payload}})
                        var payloadObject map[string]any
                        _ = json.Unmarshal(object, &payloadObject)
                        nested := payloadObject["Payload"]
                        delete(payloadObject, "Payload")
                        if fields, ok := nested.(map[string]any); ok {{
                            for key, value := range fields {{
                                payloadObject[key] = value
                            }}
                        }}
                        object, _ = json.Marshal(payloadObject)
                        data.mutex.Lock()
                        defer data.mutex.Unlock()
                        data.records[id] = object
                        writeJSON(writer, http.StatusCreated, json.RawMessage(object))
                    default:
                        writer.Header().Set("Allow", "GET, POST")
                        writeJSON(writer, http.StatusMethodNotAllowed, map[string]string{{"error": "method not allowed"}})
                    }}
                }})
                mux.HandleFunc(collection+"/", func(writer http.ResponseWriter, request *http.Request) {{
                    id := strings.TrimPrefix(request.URL.Path, collection+"/")
                    if id == "" || strings.Contains(id, "/") {{
                        writeJSON(writer, http.StatusNotFound, map[string]string{{"error": "record not found"}})
                        return
                    }}
                    switch request.Method {{
                    case http.MethodGet:
                        data.mutex.RLock()
                        current, exists := data.records[id]
                        data.mutex.RUnlock()
                        if !exists {{
                            writeJSON(writer, http.StatusNotFound, map[string]string{{"error": "record not found"}})
                            return
                        }}
                        writeJSON(writer, http.StatusOK, json.RawMessage(current))
                    case http.MethodPut:
                        data.mutex.Lock()
                        defer data.mutex.Unlock()
                        _, exists := data.records[id]
                        if !exists {{
                            writeJSON(writer, http.StatusNotFound, map[string]string{{"error": "record not found"}})
                            return
                        }}
                        payload, err := decode[T](request)
                        if err != nil {{
                            writeJSON(writer, http.StatusBadRequest, map[string]string{{"error": err.Error()}})
                            return
                        }}
                        object, _ := json.Marshal(payload)
                        var fields map[string]any
                        _ = json.Unmarshal(object, &fields)
                        fields["id"] = id
                        object, _ = json.Marshal(fields)
                        data.records[id] = object
                        writeJSON(writer, http.StatusOK, json.RawMessage(object))
                    case http.MethodDelete:
                        data.mutex.Lock()
                        defer data.mutex.Unlock()
                        _, exists := data.records[id]
                        if !exists {{
                            writeJSON(writer, http.StatusNotFound, map[string]string{{"error": "record not found"}})
                            return
                        }}
                        delete(data.records, id)
                        writeJSON(writer, http.StatusNoContent, nil)
                    default:
                        writer.Header().Set("Allow", "GET, PUT, DELETE")
                        writeJSON(writer, http.StatusMethodNotAllowed, map[string]string{{"error": "method not allowed"}})
                    }}
                }})
            }}

            func newHandler() http.Handler {{
                mux := http.NewServeMux()
                mux.HandleFunc("/health", func(writer http.ResponseWriter, request *http.Request) {{
                    if request.Method != http.MethodGet {{
                        writeJSON(writer, http.StatusMethodNotAllowed, map[string]string{{"error": "method not allowed"}})
                        return
                    }}
                    writeJSON(writer, http.StatusOK, map[string]string{{"status": "UP", "service": "{request.project_name}"}})
                }})
{indented_routes}
                return mux
            }}

            func main() {{
                port := os.Getenv("PORT")
                if port == "" {{
                    port = "{port}"
                }}
                host := os.Getenv("HOST")
                if host == "" {{
                    host = "127.0.0.1"
                }}
                server := &http.Server{{Addr: host + ":" + port, Handler: newHandler()}}
                slog.Info("service starting", "port", port)
                if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {{
                    slog.Error("service failed", "error", err)
                    os.Exit(1)
                }}
            }}
            """
        ),
        "main_test.go": _go_clean(
            f"""
            package main

            import (
                "bytes"
                "encoding/json"
                "io"
                "net/http"
                "net/http/httptest"
                "testing"
            )

            func request(t *testing.T, method string, url string, payload []byte) *httptest.ResponseRecorder {{
                t.Helper()
                var body io.Reader
                if payload != nil {{
                    body = bytes.NewReader(payload)
                }}
                request := httptest.NewRequest(method, url, body)
                request.Header.Set("Content-Type", "application/json")
                recorder := httptest.NewRecorder()
                newHandler().ServeHTTP(recorder, request)
                return recorder
            }}

            func decodeJSON(t *testing.T, payload []byte, value any) {{
                t.Helper()
                if err := json.Unmarshal(payload, value); err != nil {{
                    t.Fatal(err)
                }}
            }}

            func TestHealth(t *testing.T) {{
                result := request(t, http.MethodGet, "/health", nil)
                if result.Code != http.StatusOK {{
                    t.Fatalf("status = %d", result.Code)
                }}
            }}

{indented_tests}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {GOLANG_IMAGE} AS build
            WORKDIR /workspace
            COPY go.mod ./
            COPY *.go ./
            RUN test -z "$(gofmt -l .)" \
                && CGO_ENABLED=0 go test ./... \
                && CGO_ENABLED=0 go build -trimpath -o /out/service .

            FROM scratch
            ENV HOST=0.0.0.0
            COPY --from=build /out/service /service
            USER 10001:10001
            EXPOSE {port}
            ENTRYPOINT ["/service"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="go", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: go-ci
            on: [push, pull_request]
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: actions/setup-go@40f1582b2485089dde7abd97c1529aa768e1baff # v5
                    with:
                      go-version: 1.25.0
                  - run: test -z "$(gofmt -l .)"
                  - run: go vet ./...
                  - run: go test -race ./...
                  - run: go build ./...
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: check test build run
            check:
            \ttest -z "$$(gofmt -l .)"
            \tgo vet ./...
            test:
            \tgo test -race ./...
            build:
            \tgo build ./...
            run:
            \tPORT={port} go run .
            """
        ),
        "README.md": target_readme(
            request,
            language="Go 1.25",
            framework="net/http",
            port=port,
            commands=(
                f'test -z "$(gofmt -l .)"\ngo vet ./...\ngo test -race ./...\ngo build ./...\nPORT={port} go run .'
            ),
        ),
    }
