# ruff: noqa: E501

from __future__ import annotations

import json

from .container_images import PHP_IMAGE
from .models import SynthesisRequest
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


def render_php(request: SynthesisRequest, port: int) -> dict[str, str]:
    if request.requires_database or request.requires_authentication:
        from .php_production_target import render_php_production

        return render_php_production(request, port)
    schemas = {
        entity.plural: {
            "singular": entity.singular,
            "fields": {field.name: {"type": field.type, "required": field.required} for field in entity.fields},
        }
        for entity in request.entities
    }
    schema_php = json.dumps(schemas, ensure_ascii=False, indent=2).replace("\\", "\\\\").replace("'", "\\'")
    test_blocks: list[str] = []
    for entity in request.entities:
        sample = json.dumps(sample_payload(request, entity), ensure_ascii=False, separators=(",", ":"))
        test_blocks.append(
            clean(
                f"""
                $created = $store->create('{entity.plural}', json_decode('{sample}', true, flags: JSON_THROW_ON_ERROR));
                ensure(isset($created['id']), '{entity.singular} create did not return id');
                $id = $created['id'];
                ensure($store->get('{entity.plural}', $id) !== null, '{entity.singular} get failed');
                ensure(count($store->all('{entity.plural}')) === 1, '{entity.singular} list failed');
                ensure($store->update('{entity.plural}', $id, json_decode('{sample}', true, flags: JSON_THROW_ON_ERROR)) !== null, '{entity.singular} update failed');
                ensure($store->delete('{entity.plural}', $id), '{entity.singular} delete failed');
                ensure($store->get('{entity.plural}', $id) === null, '{entity.singular} delete was not durable');
                """
            ).rstrip()
        )
    tests = "\n".join(test_blocks)
    composer = {
        "name": f"elmos/{request.project_name}",
        "description": request.description,
        "type": "project",
        "license": "proprietary",
        "require": {"php": "8.4.*"},
        "autoload": {"psr-4": {"Generated\\": "src/"}},
        "scripts": {
            "check": ["@php -l src/Store.php", "@php -l public/index.php"],
            "test": "@php tests/run.php",
            "verify": ["@check", "@test"],
        },
        "config": {"sort-packages": True, "allow-plugins": {}},
    }
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "composer.json": json.dumps(composer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "config/entities.php": clean(
            f"""
            <?php
            declare(strict_types=1);

            return json_decode('{schema_php}', true, flags: JSON_THROW_ON_ERROR);
            """
        ),
        "src/Store.php": clean(
            """
            <?php
            declare(strict_types=1);

            namespace Generated;

            final class Store
            {
                /** @var array<string, array<string, array<string, mixed>>> */
                private array $records;

                /**
                 * @param array<string, array<string, mixed>> $schemas
                 * @param array<string, array<string, array<string, mixed>>> $seed
                 */
                public function __construct(
                    private readonly array $schemas,
                    array $seed = [],
                ) {
                    $this->records = $seed;
                    foreach (array_keys($schemas) as $resource) {
                        $this->records[$resource] ??= [];
                    }
                }

                /** @return list<array<string, mixed>> */
                public function all(string $resource): array
                {
                    $this->assertResource($resource);
                    ksort($this->records[$resource]);
                    return array_values($this->records[$resource]);
                }

                /** @return array<string, mixed>|null */
                public function get(string $resource, string $id): ?array
                {
                    $this->assertResource($resource);
                    return $this->records[$resource][$id] ?? null;
                }

                /** @param array<string, mixed> $payload @return array<string, mixed> */
                public function create(string $resource, array $payload): array
                {
                    $payload = $this->validate($resource, $payload);
                    $record = ['id' => bin2hex(random_bytes(16)), ...$payload];
                    $this->records[$resource][$record['id']] = $record;
                    return $record;
                }

                /** @param array<string, mixed> $payload @return array<string, mixed>|null */
                public function update(string $resource, string $id, array $payload): ?array
                {
                    $this->assertResource($resource);
                    if (!isset($this->records[$resource][$id])) {
                        return null;
                    }
                    $record = ['id' => $id, ...$this->validate($resource, $payload)];
                    $this->records[$resource][$id] = $record;
                    return $record;
                }

                public function delete(string $resource, string $id): bool
                {
                    $this->assertResource($resource);
                    if (!isset($this->records[$resource][$id])) {
                        return false;
                    }
                    unset($this->records[$resource][$id]);
                    return true;
                }

                /** @return array<string, array<string, array<string, mixed>>> */
                public function snapshot(): array
                {
                    return $this->records;
                }

                private function assertResource(string $resource): void
                {
                    if (!isset($this->schemas[$resource])) {
                        throw new \\InvalidArgumentException('unknown resource');
                    }
                }

                /** @param array<string, mixed> $payload @return array<string, mixed> */
                private function validate(string $resource, array $payload): array
                {
                    $this->assertResource($resource);
                    $fields = $this->schemas[$resource]['fields'];
                    if (array_diff(array_keys($payload), array_keys($fields)) !== []) {
                        throw new \\InvalidArgumentException('unknown fields');
                    }
                    foreach ($fields as $name => $specification) {
                        if ($specification['required'] && !array_key_exists($name, $payload)) {
                        throw new \\InvalidArgumentException("missing required field: {$name}");
                        }
                    }
                    return $payload;
                }
            }
            """
        ),
        "public/index.php": clean(
            f"""
            <?php
            declare(strict_types=1);

            use Generated\\Store;

            require dirname(__DIR__) . '/src/Store.php';
            $schemas = require dirname(__DIR__) . '/config/entities.php';
            $storeFile = getenv('STORE_FILE') ?: sys_get_temp_dir() . '/{request.project_name}-store.json';
            $seed = [];
            if (is_file($storeFile)) {{
                $decoded = json_decode((string) file_get_contents($storeFile), true);
                if (is_array($decoded)) $seed = $decoded;
            }}
            $store = new Store($schemas, $seed);

            function respond(int $status, mixed $body = null): never
            {{
                http_response_code($status);
                header('Content-Type: application/json; charset=utf-8');
                if ($body !== null) echo json_encode($body, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
                exit;
            }}

            function persist(Store $store, string $path): void
            {{
                $temporary = $path . '.tmp';
                file_put_contents($temporary, json_encode($store->snapshot(), JSON_THROW_ON_ERROR), LOCK_EX);
                rename($temporary, $path);
            }}

            $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
            $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
            if ($method === 'GET' && $path === '/health') {{
                respond(200, ['status' => 'UP', 'service' => '{request.project_name}']);
            }}
            $parts = array_values(array_filter(explode('/', trim((string) $path, '/'))));
            if (count($parts) < 3 || $parts[0] !== 'api' || $parts[1] !== 'v1') respond(404, ['error' => 'not found']);
            $resource = $parts[2];
            $id = $parts[3] ?? null;
            try {{
                if ($method === 'GET' && $id === null) respond(200, $store->all($resource));
                if ($method === 'GET' && $id !== null) {{
                    $record = $store->get($resource, $id);
                    $record === null ? respond(404, ['error' => 'record not found']) : respond(200, $record);
                }}
                if ($method === 'POST' && $id === null) {{
                    $payload = json_decode((string) file_get_contents('php://input'), true, flags: JSON_THROW_ON_ERROR);
                    $record = $store->create($resource, $payload);
                    persist($store, $storeFile);
                    respond(201, $record);
                }}
                if ($method === 'PUT' && $id !== null) {{
                    $payload = json_decode((string) file_get_contents('php://input'), true, flags: JSON_THROW_ON_ERROR);
                    $record = $store->update($resource, $id, $payload);
                    if ($record === null) respond(404, ['error' => 'record not found']);
                    persist($store, $storeFile);
                    respond(200, $record);
                }}
                if ($method === 'DELETE' && $id !== null) {{
                    if (!$store->delete($resource, $id)) respond(404, ['error' => 'record not found']);
                    persist($store, $storeFile);
                    respond(204);
                }}
                respond(405, ['error' => 'method not allowed']);
            }} catch (\\InvalidArgumentException|\\JsonException $error) {{
                respond(400, ['error' => $error->getMessage()]);
            }}
            """
        ),
        "tests/run.php": clean(
            f"""
            <?php
            declare(strict_types=1);

            use Generated\\Store;

            require dirname(__DIR__) . '/src/Store.php';
            $schemas = require dirname(__DIR__) . '/config/entities.php';
            $store = new Store($schemas);

            function ensure(bool $condition, string $message): void
            {{
                if (!$condition) throw new RuntimeException($message);
            }}

            {tests}
            echo "PHP CRUD tests passed\\n";
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {PHP_IMAGE}
            RUN addgroup -S app && adduser -S -G app -u 10001 app
            WORKDIR /app
            COPY . .
            RUN php -l src/Store.php && php -l public/index.php && php tests/run.php
            USER 10001:10001
            EXPOSE {port}
            CMD ["php", "-S", "0.0.0.0:{port}", "public/index.php"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="php", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: php-ci
            on: [push, pull_request]
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: shivammathur/setup-php@f3e473d116dcccaddc5834248c87452386958240 # v2
                    with:
                      php-version: '8.4.12'
                  - run: php -l src/Store.php
                  - run: php -l public/index.php
                  - run: php tests/run.php
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: check test run
            check:
            \tphp -l src/Store.php
            \tphp -l public/index.php
            test:
            \tphp tests/run.php
            run:
            \tPORT={port} php -S 127.0.0.1:{port} public/index.php
            """
        ),
        "README.md": target_readme(
            request,
            language="PHP 8.4",
            framework="Native HTTP modular service",
            port=port,
            commands=f"php -l src/Store.php\nphp tests/run.php\nphp -S 127.0.0.1:{port} public/index.php",
        ),
    }
