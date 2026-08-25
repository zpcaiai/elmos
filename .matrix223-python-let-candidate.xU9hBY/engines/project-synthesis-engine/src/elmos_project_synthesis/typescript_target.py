# ruff: noqa: E501

from __future__ import annotations

import json

from .container_images import NODE_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal
from .rendering import (
    camel,
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    sample_payload,
    target_readme,
)


def _typescript_type(field: FieldSpec) -> str:
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "datetime": "string",
    }[field.type]


def _dto(entity: EntitySpec) -> str:
    entity_class = pascal(entity.singular)
    fields = "\n".join(
        f"  {camel(field.name)}{'?' if not field.required else ''}: {_typescript_type(field)};"
        for field in entity.fields
    )
    return clean(
        f"""
        export type {entity_class}Upsert = {{
        {fields}
        }};

        export type {entity_class} = {entity_class}Upsert & {{ id: string }};
        """
    ).rstrip()


def render_typescript(request: SynthesisRequest, port: int) -> dict[str, str]:
    if request.requires_database or request.requires_authentication:
        from .typescript_production_target import render_typescript_production

        return render_typescript_production(request, port)
    dto_blocks = "\n\n".join(_dto(entity) for entity in request.entities)
    imports = ", ".join(
        name for entity in request.entities for name in (pascal(entity.singular), f"{pascal(entity.singular)}Upsert")
    )
    stores: list[str] = []
    methods: list[str] = []
    test_blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        upsert_class = f"{entity_class}Upsert"
        store_name = f"{camel(entity.plural)}Store"
        stores.append(f"  private readonly {store_name} = new Map<string, {entity_class}>();")
        required_checks = (
            " || ".join(
                f'(typeof payload.{camel(field.name)} !== "{_typescript_type(field)}")'
                for field in entity.fields
                if field.required
            )
            or "false"
        )
        methods.append(
            clean(
                f"""
                @Get("/api/v1/{entity.plural}")
                list{entity_class}(): {entity_class}[] {{
                  return [...this.{store_name}.values()].sort((left, right) => left.id.localeCompare(right.id));
                }}

                @Get("/api/v1/{entity.plural}/:id")
                get{entity_class}(@Param("id") id: string): {entity_class} {{
                  const record = this.{store_name}.get(id);
                  if (!record) throw new NotFoundException("record not found");
                  return record;
                }}

                @Post("/api/v1/{entity.plural}")
                @HttpCode(201)
                create{entity_class}(@Body() payload: {upsert_class}): {entity_class} {{
                  this.validate{entity_class}(payload);
                  const record = {{ id: randomUUID(), ...payload }};
                  this.{store_name}.set(record.id, record);
                  return record;
                }}

                @Put("/api/v1/{entity.plural}/:id")
                update{entity_class}(@Param("id") id: string, @Body() payload: {upsert_class}): {entity_class} {{
                  if (!this.{store_name}.has(id)) throw new NotFoundException("record not found");
                  this.validate{entity_class}(payload);
                  const record = {{ id, ...payload }};
                  this.{store_name}.set(id, record);
                  return record;
                }}

                @Delete("/api/v1/{entity.plural}/:id")
                @HttpCode(204)
                delete{entity_class}(@Param("id") id: string): void {{
                  if (!this.{store_name}.delete(id)) throw new NotFoundException("record not found");
                }}

                private validate{entity_class}(payload: {upsert_class}): void {{
                  if (!payload || {required_checks}) {{
                    throw new BadRequestException("required fields are missing or invalid");
                  }}
                }}
                """
            ).rstrip()
        )
        sample = json.dumps(sample_payload(request, entity), ensure_ascii=False, separators=(",", ":"))
        test_blocks.append(
            clean(
                f"""
                it("{entity.singular} full CRUD", async () => {{
                  const created = await app.inject({{
                    method: "POST",
                    url: "/api/v1/{entity.plural}",
                    payload: {sample},
                  }});
                  assert.equal(created.statusCode, 201);
                  const id = created.json().id as string;
                  assert.equal((await app.inject({{ method: "GET", url: `/api/v1/{entity.plural}/${{id}}` }})).statusCode, 200);
                  assert.equal((await app.inject({{
                    method: "PUT",
                    url: `/api/v1/{entity.plural}/${{id}}`,
                    payload: {sample},
                  }})).statusCode, 200);
                  assert.equal((await app.inject({{ method: "DELETE", url: `/api/v1/{entity.plural}/${{id}}` }})).statusCode, 204);
                  assert.equal((await app.inject({{ method: "GET", url: `/api/v1/{entity.plural}/${{id}}` }})).statusCode, 404);
                }});
                """
            ).rstrip()
        )
    controller_methods = "\n\n".join(methods)
    tests = "\n\n".join(test_blocks)
    package_json = {
        "name": request.project_name,
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "packageManager": "pnpm@10.12.4",
        "scripts": {
            "build": "tsc -p tsconfig.json",
            "check": "tsc --noEmit -p tsconfig.json",
            "test": "tsx --test tests/**/*.test.ts",
            "start": "node dist/main.js",
            "dev": "tsx src/main.ts",
        },
        "dependencies": {
            "@nestjs/common": "11.1.6",
            "@nestjs/core": "11.1.6",
            "@nestjs/platform-fastify": "11.1.6",
            "fastify": "5.6.1",
            "reflect-metadata": "0.2.2",
            "rxjs": "7.8.2",
        },
        "devDependencies": {
            "@types/node": "24.3.0",
            "tsx": "4.20.5",
            "typescript": "5.9.2",
        },
    }
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "package.json": json.dumps(package_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "tsconfig.json": clean(
            """
            {
              "compilerOptions": {
                "target": "ES2022",
                "module": "NodeNext",
                "moduleResolution": "NodeNext",
                "strict": true,
                "noUncheckedIndexedAccess": true,
                "experimentalDecorators": true,
                "emitDecoratorMetadata": true,
                "outDir": "dist",
                "rootDir": "src",
                "skipLibCheck": true
              },
              "include": ["src/**/*.ts"]
            }
            """
        ),
        "src/models.ts": dto_blocks + "\n",
        "src/app.controller.ts": clean(
            f"""
            import {{ randomUUID }} from "node:crypto";
            import {{
              BadRequestException,
              Body,
              Controller,
              Delete,
              Get,
              HttpCode,
              NotFoundException,
              Param,
              Post,
              Put,
            }} from "@nestjs/common";
            import type {{ {imports} }} from "./models.js";

            @Controller()
            export class AppController {{
              {chr(10).join(stores)}

              @Get("/health")
              health(): {{ status: "UP"; service: string }} {{
                return {{ status: "UP", service: "{request.project_name}" }};
              }}

            {controller_methods}
            }}
            """
        ),
        "src/app.module.ts": clean(
            """
            import { Module } from "@nestjs/common";
            import { AppController } from "./app.controller.js";

            @Module({ controllers: [AppController] })
            export class AppModule {}
            """
        ),
        "src/bootstrap.ts": clean(
            """
            import "reflect-metadata";
            import { NestFactory } from "@nestjs/core";
            import { FastifyAdapter, type NestFastifyApplication } from "@nestjs/platform-fastify";
            import { AppModule } from "./app.module.js";

            export async function createApplication(): Promise<NestFastifyApplication> {
              const app = await NestFactory.create<NestFastifyApplication>(
                AppModule,
                new FastifyAdapter({ logger: false }),
                { logger: false },
              );
              await app.init();
              await app.getHttpAdapter().getInstance().ready();
              return app;
            }
            """
        ),
        "src/main.ts": clean(
            f"""
            import {{ createApplication }} from "./bootstrap.js";

            const app = await createApplication();
            const port = Number.parseInt(process.env.PORT ?? "{port}", 10);
            const host = process.env.HOST ?? "127.0.0.1";
            await app.listen(port, host);
            """
        ),
        "tests/api.test.ts": clean(
            f"""
            import assert from "node:assert/strict";
            import {{ after, before, it }} from "node:test";
            import type {{ NestFastifyApplication }} from "@nestjs/platform-fastify";
            import {{ createApplication }} from "../src/bootstrap.js";

            let app: NestFastifyApplication;
            before(async () => {{ app = await createApplication(); }});
            after(async () => {{ await app.close(); }});

            it("health", async () => {{
              const response = await app.inject({{ method: "GET", url: "/health" }});
              assert.equal(response.statusCode, 200);
              assert.equal(response.json().status, "UP");
            }});

            {tests}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {NODE_IMAGE} AS build
            RUN corepack enable
            WORKDIR /app
            COPY package.json pnpm-lock.yaml ./
            RUN pnpm install --frozen-lockfile
            COPY tsconfig.json ./
            COPY src ./src
            RUN pnpm build

            FROM {NODE_IMAGE}
            ENV HOST=0.0.0.0
            RUN corepack enable && addgroup -S app && adduser -S -G app -u 10001 app
            WORKDIR /app
            COPY --from=build /app/package.json /app/pnpm-lock.yaml ./
            COPY --from=build /app/node_modules ./node_modules
            COPY --from=build /app/dist ./dist
            USER 10001:10001
            EXPOSE {port}
            CMD ["node", "dist/main.js"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="typescript", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: typescript-ci
            on: [push, pull_request]
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: pnpm/action-setup@b906affcce14559ad1aafd4ab0e942779e9f58b1 # v4
                    with:
                      version: 10.12.4
                  - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4
                    with:
                      node-version: 26.0.0
                      cache: pnpm
                  - run: pnpm install --frozen-lockfile
                  - run: pnpm check
                  - run: pnpm test
                  - run: pnpm build
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: lock sync test check build run
            lock:
            \tpnpm install --lockfile-only
            sync:
            \tpnpm install --frozen-lockfile
            test:
            \tpnpm test
            check:
            \tpnpm check
            build:
            \tpnpm build
            run:
            \tPORT={port} pnpm start
            """
        ),
        "README.md": target_readme(
            request,
            language="TypeScript 5.9 / Node 26",
            framework="NestJS 11.1.6 + Fastify 5.6.1",
            port=port,
            commands=f"pnpm install --frozen-lockfile\npnpm test\npnpm build\nPORT={port} pnpm start",
        ),
    }
