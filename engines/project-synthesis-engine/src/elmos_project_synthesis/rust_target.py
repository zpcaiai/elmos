# ruff: noqa: E501

from __future__ import annotations

import json
from textwrap import indent

from .container_images import ALPINE_IMAGE, RUST_IMAGE
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


def _rust_type(field: FieldSpec) -> str:
    base = {
        "string": "String",
        "integer": "i64",
        "number": "f64",
        "boolean": "bool",
        "datetime": "String",
    }[field.type]
    return base if field.required else f"Option<{base}>"


def _rust_route(path: str, handler: str) -> str:
    single_line = f'.route("{path}", {handler})'
    arguments = f'"{path}", {handler}'
    if len(arguments) <= 60 and 8 + len(single_line) < 100:
        return single_line
    if len(handler) <= 60 and 12 + len(handler) < 100:
        rendered_handler = f"    {handler},"
    else:
        methods = handler.split(".")
        rendered_handler = "\n".join(
            [f"    {methods[0]}", *(f"        .{method}" for method in methods[1:-1]), f"        .{methods[-1]},"]
        )
    return "\n".join((".route(", f'    "{path}",', rendered_handler, ")"))


def _rust_status_call(method: str, uri: str, payload: str | None) -> str:
    arguments = f"&app, Method::{method}, {uri}, {f'Some({payload})' if payload else 'None'}"
    single_line = f"call({arguments}).await.status(),"
    if 8 + len(single_line) <= 100:
        return single_line
    return "\n".join(
        (
            "call(",
            "    &app,",
            f"    Method::{method},",
            f"    {uri},",
            f"    {f'Some({payload})' if payload else 'None'}",
            ")",
            ".await",
            ".status(),",
        )
    )


def render_rust(request: SynthesisRequest, port: int) -> dict[str, str]:
    model_blocks: list[str] = []
    state_fields: list[str] = []
    route_lines: list[str] = []
    handler_blocks: list[str] = []
    test_blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        upsert = f"{entity_class}Upsert"
        fields = "\n".join(f"    pub {field.name}: {_rust_type(field)}," for field in entity.fields)
        record_fields = "\n".join(f"    pub {field.name}: {_rust_type(field)}," for field in entity.fields)
        copy_args = "\n".join(f"        {field.name}: payload.{field.name}," for field in entity.fields)
        indented_fields = indent(fields, "                ")
        indented_record_fields = indent(record_fields, "                ")
        indented_copy_args = indent(copy_args, "                ")
        state_name = entity.plural
        model_blocks.append(
            clean(
                f"""
                #[derive(Clone, Debug, Deserialize, Serialize)]
                pub struct {upsert} {{
{indented_fields}
                }}

                #[derive(Clone, Debug, Deserialize, Serialize)]
                pub struct {entity_class} {{
                    pub id: String,
{indented_record_fields}
                }}
                """
            ).rstrip()
        )
        state_fields.append(f"    pub {state_name}: Arc<RwLock<HashMap<String, {entity_class}>>>,")
        route_lines.append(
            _rust_route(
                f"/api/v1/{entity.plural}",
                f"get(list_{entity.plural}).post(create_{entity.singular})",
            )
        )
        route_lines.append(
            _rust_route(
                f"/api/v1/{entity.plural}/{{id}}",
                (f"get(get_{entity.singular}).put(update_{entity.singular}).delete(delete_{entity.singular})"),
            )
        )
        handler_blocks.append(
            clean(
                f"""
                async fn list_{entity.plural}(State(state): State<AppState>) -> Json<Vec<{entity_class}>> {{
                    let records = state.{state_name}.read().await;
                    let mut values: Vec<_> = records.values().cloned().collect();
                    values.sort_by(|left, right| left.id.cmp(&right.id));
                    Json(values)
                }}

                async fn get_{entity.singular}(
                    State(state): State<AppState>,
                    Path(id): Path<String>,
                ) -> Result<Json<{entity_class}>, StatusCode> {{
                    state
                        .{state_name}
                        .read()
                        .await
                        .get(&id)
                        .cloned()
                        .map(Json)
                        .ok_or(StatusCode::NOT_FOUND)
                }}

                async fn create_{entity.singular}(
                    State(state): State<AppState>,
                    Json(payload): Json<{upsert}>,
                ) -> (StatusCode, Json<{entity_class}>) {{
                    let record = {entity_class} {{
                        id: Uuid::new_v4().to_string(),
{indented_copy_args}
                    }};
                    state
                        .{state_name}
                        .write()
                        .await
                        .insert(record.id.clone(), record.clone());
                    (StatusCode::CREATED, Json(record))
                }}

                async fn update_{entity.singular}(
                    State(state): State<AppState>,
                    Path(id): Path<String>,
                    Json(payload): Json<{upsert}>,
                ) -> Result<Json<{entity_class}>, StatusCode> {{
                    let mut records = state.{state_name}.write().await;
                    if !records.contains_key(&id) {{
                        return Err(StatusCode::NOT_FOUND);
                    }}
                    let record = {entity_class} {{
                        id: id.clone(),
{indented_copy_args}
                    }};
                    records.insert(id, record.clone());
                    Ok(Json(record))
                }}

                async fn delete_{entity.singular}(State(state): State<AppState>, Path(id): Path<String>) -> StatusCode {{
                    if state.{state_name}.write().await.remove(&id).is_some() {{
                        StatusCode::NO_CONTENT
                    }} else {{
                        StatusCode::NOT_FOUND
                    }}
                }}
                """
            ).rstrip()
        )
        sample = json.dumps(sample_payload(request, entity), ensure_ascii=False, separators=(",", ":"))
        rust_sample = json.dumps(sample)
        update_call = indent(_rust_status_call("PUT", "&uri", rust_sample), "                    ")
        test_blocks.append(
            clean(
                f"""
                let created = call(
                    &app,
                    Method::POST,
                    "/api/v1/{entity.plural}",
                    Some({rust_sample}),
                )
                .await;
                assert_eq!(created.status(), StatusCode::CREATED);
                let body = to_bytes(created.into_body(), 1 << 20).await.unwrap();
                let record: Value = serde_json::from_slice(&body).unwrap();
                let id = record["id"].as_str().unwrap();
                let uri = format!("/api/v1/{entity.plural}/{{id}}");
                assert_eq!(
                    call(&app, Method::GET, &uri, None).await.status(),
                    StatusCode::OK
                );
                assert_eq!(
{update_call}
                    StatusCode::OK
                );
                assert_eq!(
                    call(&app, Method::DELETE, &uri, None).await.status(),
                    StatusCode::NO_CONTENT
                );
                assert_eq!(
                    call(&app, Method::GET, &uri, None).await.status(),
                    StatusCode::NOT_FOUND
                );
                """
            ).rstrip()
        )
    models = "\n\n".join(model_blocks)
    rendered_state_fields = "\n".join(state_fields)
    routes = indent("\n".join(route_lines), "        ")
    handlers = "\n\n".join(handler_blocks)
    tests = "\n\n".join(test_blocks)
    indented_models = indent(models, "            ")
    indented_state_fields = indent(rendered_state_fields, "            ")
    indented_routes = indent(routes, "            ")
    indented_handlers = indent(handlers, "            ")
    indented_tests = indent(tests, "                ")
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "Cargo.toml": clean(
            f"""
            [package]
            name = "{request.project_name}"
            version = "1.0.0"
            edition = "2024"
            rust-version = "1.89"
            description = {json.dumps(request.description, ensure_ascii=False)}

            [dependencies]
            axum = "=0.8.4"
            serde = {{ version = "=1.0.219", features = ["derive"] }}
            serde_json = "=1.0.143"
            tokio = {{ version = "=1.47.1", features = ["macros", "net", "rt-multi-thread", "signal", "sync"] }}
            uuid = {{ version = "=1.18.0", features = ["v4"] }}

            [dev-dependencies]
            tower = {{ version = "=0.5.2", features = ["util"] }}

            [profile.release]
            strip = true
            lto = "thin"
            codegen-units = 1
            """
        ),
        "rust-toolchain.toml": clean(
            """
            [toolchain]
            channel = "1.89.0"
            components = ["clippy", "rustfmt"]
            profile = "minimal"
            """
        ),
        "src/lib.rs": clean(
            f"""
            use axum::{{
                Json, Router,
                extract::{{Path, State}},
                http::StatusCode,
                routing::get,
            }};
            use serde::{{Deserialize, Serialize}};
            use std::{{collections::HashMap, sync::Arc}};
            use tokio::sync::RwLock;
            use uuid::Uuid;

{indented_models}

            #[derive(Clone, Default)]
            pub struct AppState {{
{indented_state_fields}
            }}

            pub fn application() -> Router {{
                Router::new()
                    .route(
                        "/health",
                        get(|| async {{
                            Json(serde_json::json!({{"status": "UP", "service": "{request.project_name}"}}))
                        }}),
                    )
{indented_routes}
                    .with_state(AppState::default())
            }}

{indented_handlers}
            """
        ),
        "src/main.rs": clean(
            f"""
            use {request.project_name.replace("-", "_")}::application;
            use std::env;
            use tokio::net::TcpListener;

            #[tokio::main]
            async fn main() {{
                let port = env::var("PORT").unwrap_or_else(|_| "{port}".to_owned());
                let host = env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_owned());
                let listener = TcpListener::bind(format!("{{host}}:{{port}}"))
                    .await
                    .expect("bind service");
                axum::serve(listener, application())
                    .await
                    .expect("serve application");
            }}
            """
        ),
        "tests/api.rs": clean(
            f"""
            use axum::{{
                Router,
                body::{{Body, to_bytes}},
                http::{{Method, Request, StatusCode}},
                response::Response,
            }};
            use {request.project_name.replace("-", "_")}::application;
            use serde_json::Value;
            use tower::ServiceExt;

            async fn call(app: &Router, method: Method, uri: &str, payload: Option<&str>) -> Response {{
                let mut request = Request::builder().method(method).uri(uri);
                if payload.is_some() {{
                    request = request.header("content-type", "application/json");
                }}
                let body = payload.map_or_else(Body::empty, |value| Body::from(value.to_owned()));
                app.clone()
                    .oneshot(request.body(body).unwrap())
                    .await
                    .unwrap()
            }}

            #[tokio::test]
            async fn full_crud_and_health_journey() {{
                let app = application();
                assert_eq!(
                    call(&app, Method::GET, "/health", None).await.status(),
                    StatusCode::OK
                );
{indented_tests}
            }}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {RUST_IMAGE} AS build
            RUN apk add --no-cache musl-dev
            WORKDIR /workspace
            COPY . .
            RUN cargo generate-lockfile \
                && cargo fmt --check \
                && cargo clippy --locked --all-targets --all-features -- -D warnings \
                && cargo test --locked --all-features \
                && cargo build --locked --release

            FROM {ALPINE_IMAGE}
            ENV HOST=0.0.0.0
            RUN addgroup -S app && adduser -S -G app -u 10001 app
            COPY --from=build /workspace/target/release/{request.project_name} /service
            USER 10001:10001
            EXPOSE {port}
            ENTRYPOINT ["/service"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="rust", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: rust-ci
            on: [push, pull_request]
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: dtolnay/rust-toolchain@451ce45ce31d200b52705aadd15ce75018b006de # 1.89.0
                    with:
                      components: clippy,rustfmt
                  - run: cargo generate-lockfile
                  - run: cargo fmt --check
                  - run: cargo clippy --locked --all-targets --all-features -- -D warnings
                  - run: cargo test --locked --all-features
                  - run: cargo build --locked --release
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: lock check test build run
            lock:
            \tcargo generate-lockfile
            check:
            \tcargo fmt --check
            \tcargo clippy --locked --all-targets --all-features -- -D warnings
            test:
            \tcargo test --locked --all-features
            build:
            \tcargo build --locked --release
            run:
            \tPORT={port} cargo run --locked
            """
        ),
        "README.md": target_readme(
            request,
            language="Rust 1.89",
            framework="Axum 0.8.4",
            port=port,
            commands=(
                f"cargo generate-lockfile\ncargo fmt --check\ncargo clippy --locked --all-targets --all-features -- -D warnings\n"
                f"cargo test --locked --all-features\nPORT={port} cargo run --locked"
            ),
        ),
    }
