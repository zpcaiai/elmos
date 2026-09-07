# ruff: noqa: E501
"""PHP production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

Same shared contract and harness as the Python, Java, Go, TypeScript, C#,
Kotlin and Rust profiles. The store speaks PDO directly so the tenant binding
stays visible rather than hidden behind an ORM session.

PHP source is assembled by ``__TOKEN__`` substitution rather than f-strings:
the generated code is dense with ``{}`` and ``$``, and escaping every one of
them to survive ``str.format`` turns a readable template into a defect factory.

The exact toolchain is built with ``--disable-all``, so this emitter may only
use what ``install_project_synthesis_toolchains.sh`` explicitly compiles in:
``json``, ``hash``, ``PDO``, ``pdo_pgsql`` and ``openssl``. Two consequences
are load-bearing:

* There is no ``ext-filter``, so no ``filter_var``. UUID and payload checks are
  done with ``preg_match`` from ``ext-pcre``, which is always present.
* RS256 verification goes through ``openssl_verify``. The build has neither
  ``gmp`` nor ``bcmath``, so a pure-PHP RSA fallback is not an option -- the
  toolchain script therefore treats ``openssl`` as a required extension and
  refuses a build that lacks it.
"""
from __future__ import annotations

import json

from .container_images import PHP_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest
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

PHP_VERSION = "8.4.12"

REQUIRED_EXTENSIONS = ("json", "hash", "PDO", "pdo_pgsql", "openssl")


def _php_literal(value: object) -> str:
    """Render a Python value as a PHP literal via JSON.

    PHP's array syntax accepts JSON object and array literals for scalars, and
    going through ``json.dumps`` keeps quoting and unicode escaping correct
    without hand-rolling an encoder.
    """
    return json.dumps(value, ensure_ascii=False)


def _cast_from_database(field: FieldSpec, expression: str) -> str:
    """Coerce a PDO column to the JSON type the shared contract declares.

    PDO's pgsql driver returns every column as a string unless the value is
    NULL, so without these casts an ``integer`` field would serialise as
    ``"1"`` and fail the contract that every other target satisfies.
    """
    if field.type == "integer":
        return f"(int) {expression}"
    if field.type == "number":
        return f"(float) {expression}"
    if field.type == "boolean":
        # pdo_pgsql renders booleans as 't'/'f'.
        return f"({expression} === 't' || {expression} === true)"
    return f"(string) {expression}"


def _bind_value(field: FieldSpec) -> str:
    if field.type == "boolean":
        return f"$payload[{_php_literal(field.name)}] ? 't' : 'f'"
    return f"$payload[{_php_literal(field.name)}]"


def _sample_json(field: FieldSpec) -> object:
    return {
        "string": f"sample-{field.name}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


_SECURITY_JWT = """
    private function verify(string $signingInput, string $signature, array $header): bool
    {
        if (($header['alg'] ?? '') !== 'HS256') {
            return false;
        }
        $path = self::requiredEnvironment(__ENV_JWT_SECRET_FILE__);
        $secret = trim((string) file_get_contents($path));
        if (strlen($secret) < 32) {
            throw new RuntimeException('JWT_SECRET_TOO_SHORT');
        }
        $expected = hash_hmac('sha256', $signingInput, $secret, true);

        return hash_equals($expected, $signature);
    }
"""

_SECURITY_OIDC = """
    private function verify(string $signingInput, string $signature, array $header): bool
    {
        if (($header['alg'] ?? '') !== 'RS256') {
            return false;
        }
        $document = json_decode(
            (string) file_get_contents(self::requiredEnvironment(__ENV_OIDC_JWKS_FILE__)),
            true,
        );
        $keys = $document['keys'] ?? null;
        if (!is_array($keys) || count($keys) !== 1) {
            throw new RuntimeException('OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_KEY');
        }
        $public = openssl_pkey_get_public(self::publicKeyPem($keys[0]));
        if ($public === false) {
            throw new RuntimeException('OIDC_JWKS_PUBLIC_KEY_UNUSABLE');
        }

        return openssl_verify($signingInput, $signature, $public, OPENSSL_ALGO_SHA256) === 1;
    }

    /**
     * Rebuild a PEM public key from the JWKS modulus and exponent.
     *
     * openssl_pkey_get_public() will not read a JWK, so the RSAPublicKey
     * SEQUENCE is DER-encoded here and wrapped as PEM.
     */
    private static function publicKeyPem(array $key): string
    {
        $modulus = self::base64UrlDecode((string) ($key['n'] ?? ''));
        $exponent = self::base64UrlDecode((string) ($key['e'] ?? ''));
        if ($modulus === '' || $exponent === '') {
            throw new RuntimeException('OIDC_JWKS_KEY_INCOMPLETE');
        }
        $sequence = self::derInteger($modulus) . self::derInteger($exponent);
        $rsaKey = self::derWrap(0x30, $sequence);
        $algorithm = self::derWrap(
            0x30,
            self::derWrap(0x06, base64_decode('KoZIhvcNAQEB')) . self::derWrap(0x05, ''),
        );
        $bitString = self::derWrap(0x03, chr(0) . $rsaKey);
        $info = self::derWrap(0x30, $algorithm . $bitString);

        return "-----BEGIN PUBLIC KEY-----\\n"
            . chunk_split(base64_encode($info), 64, "\\n")
            . "-----END PUBLIC KEY-----\\n";
    }

    private static function derInteger(string $bytes): string
    {
        $bytes = ltrim($bytes, chr(0));
        if ($bytes === '' || (ord($bytes[0]) & 0x80) !== 0) {
            // A leading high bit would be read as a negative number.
            $bytes = chr(0) . $bytes;
        }

        return self::derWrap(0x02, $bytes);
    }

    private static function derWrap(int $tag, string $contents): string
    {
        $length = strlen($contents);
        if ($length < 0x80) {
            $header = chr($length);
        } else {
            $encoded = ltrim(pack('N', $length), chr(0));
            $header = chr(0x80 | strlen($encoded)) . $encoded;
        }

        return chr($tag) . $header . $contents;
    }
"""

_SECURITY_SOURCE = """
<?php

declare(strict_types=1);

namespace __NAMESPACE__;

use RuntimeException;

/**
 * Bearer verification for the production profile.
 *
 * A structurally valid signature is not authorization: issuer, audience,
 * expiry and the tenant claim the database policy is keyed on are all
 * mandatory, so a token minted for another service or another tenant is
 * refused here rather than becoming a cross-tenant read.
 */
final class TenantAuthenticator
{
    public static function requiredEnvironment(string $name): string
    {
        $value = getenv($name);
        if ($value === false || trim($value) === '') {
            throw new RuntimeException('REQUIRED_ENVIRONMENT_MISSING:' . $name);
        }

        return $value;
    }

    /** Returns the tenant a request is entitled to, or null for any token that fails verification. */
    public function tenantFrom(?string $authorization): ?string
    {
        if ($authorization === null || !str_starts_with($authorization, 'Bearer ')) {
            return null;
        }
        $segments = explode('.', substr($authorization, 7));
        if (count($segments) !== 3) {
            return null;
        }
        [$encodedHeader, $encodedPayload, $encodedSignature] = $segments;
        $header = json_decode(self::base64UrlDecode($encodedHeader), true);
        $claims = json_decode(self::base64UrlDecode($encodedPayload), true);
        if (!is_array($header) || !is_array($claims)) {
            return null;
        }
        $signature = self::base64UrlDecode($encodedSignature);
        if ($signature === '' || !$this->verify($encodedHeader . '.' . $encodedPayload, $signature, $header)) {
            return null;
        }
        if (!$this->claimsAcceptable($claims)) {
            return null;
        }
        $tenant = $claims[__TENANT_CLAIM__] ?? null;

        return is_string($tenant) && trim($tenant) !== '' ? $tenant : null;
    }

    /**
     * Expiry, issuer and audience are all mandatory and checked without
     * leeway. A token missing any of them is refused rather than treated as
     * unconstrained.
     */
    private function claimsAcceptable(array $claims): bool
    {
        $expiry = $claims['exp'] ?? null;
        if (!is_int($expiry) && !is_float($expiry)) {
            return false;
        }
        if ((int) $expiry <= time()) {
            return false;
        }
        if (($claims['iss'] ?? null) !== self::requiredEnvironment(__ENV_AUTH_ISSUER__)) {
            return false;
        }
        $audience = $claims['aud'] ?? null;
        $expected = self::requiredEnvironment(__ENV_AUTH_AUDIENCE__);
        $accepted = is_array($audience) ? $audience : [$audience];

        return in_array($expected, $accepted, true);
    }

    private static function base64UrlDecode(string $value): string
    {
        $decoded = base64_decode(strtr($value, '-_', '+/'), true);

        return $decoded === false ? '' : $decoded;
    }
__VERIFY__}
"""

_STORE_SOURCE = """
<?php

declare(strict_types=1);

namespace __NAMESPACE__;

use PDO;
use PDOException;
use RuntimeException;

/**
 * Every statement runs inside one tenant-scoped transaction.
 *
 * __TENANT_SETTING__ is applied with set_config(..., true) so it is
 * transaction local and cannot leak to the next borrower of a pooled
 * connection. Row level security is FORCED on every table, so that binding --
 * not the SQL text -- confines a request to its tenant.
 */
final class __ENTITY__Store
{
    private const LIST_SQL = __LIST_SQL__;
    private const GET_SQL = __GET_SQL__;
    private const UPSERT_SQL = __UPSERT_SQL__;
    private const DELETE_SQL = __DELETE_SQL__;
    private const BIND_TENANT_SQL = __BIND_TENANT_SQL__;

    public function __construct(private readonly string $databaseUrl)
    {
    }

    private function connect(): PDO
    {
        $parts = parse_url($this->databaseUrl);
        if ($parts === false || ($parts['scheme'] ?? '') !== 'postgresql') {
            throw new RuntimeException('DATABASE_URL_SCHEME_UNSUPPORTED');
        }
        $dsn = sprintf(
            'pgsql:host=%s;port=%d;dbname=%s',
            $parts['host'] ?? '127.0.0.1',
            $parts['port'] ?? 5432,
            ltrim($parts['path'] ?? '', '/'),
        );

        return new PDO($dsn, urldecode($parts['user'] ?? ''), urldecode($parts['pass'] ?? ''), [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    }

    /** @return array<int, mixed> */
    private function inTenant(string $tenant, callable $work): mixed
    {
        if (trim($tenant) === '') {
            throw new RuntimeException('TENANT_ID_REQUIRED');
        }
        $connection = $this->connect();
        $connection->beginTransaction();
        try {
            $connection->prepare(self::BIND_TENANT_SQL)->execute([$tenant]);
            $result = $work($connection);
            $connection->commit();

            return $result;
        } catch (PDOException $error) {
            $connection->rollBack();

            throw $error;
        }
    }

    /** @return array<int, array<string, mixed>> */
    public function list(string $tenant): array
    {
        return $this->inTenant($tenant, static function (PDO $connection): array {
            $statement = $connection->prepare(self::LIST_SQL);
            $statement->execute();
            $records = [];
            while ($row = $statement->fetch(PDO::FETCH_ASSOC)) {
                $records[] = self::hydrate($row);
            }

            return $records;
        });
    }

    /** @return array<string, mixed>|null */
    public function find(string $tenant, string $id): ?array
    {
        return $this->inTenant($tenant, static function (PDO $connection) use ($id): ?array {
            $statement = $connection->prepare(self::GET_SQL);
            $statement->execute([$id]);
            $row = $statement->fetch(PDO::FETCH_ASSOC);

            return $row === false ? null : self::hydrate($row);
        });
    }

    /**
     * @param array<string, mixed> $payload
     * @return array<string, mixed>
     */
    public function save(string $tenant, string $id, array $payload): array
    {
        return $this->inTenant($tenant, static function (PDO $connection) use ($tenant, $id, $payload): array {
            $statement = $connection->prepare(self::UPSERT_SQL);
            $statement->execute([$tenant, $id, __BIND_VALUES__]);
            $row = $statement->fetch(PDO::FETCH_ASSOC);
            if ($row === false) {
                throw new RuntimeException('UPSERT_RETURNED_NO_ROW');
            }

            return self::hydrate($row);
        });
    }

    public function delete(string $tenant, string $id): bool
    {
        return $this->inTenant($tenant, static function (PDO $connection) use ($id): bool {
            $statement = $connection->prepare(self::DELETE_SQL);
            $statement->execute([$id]);

            return $statement->rowCount() > 0;
        });
    }

    /**
     * pdo_pgsql hands every column back as a string, so each one is cast to
     * the type the shared contract declares before it reaches JSON.
     *
     * @param array<string, mixed> $row
     * @return array<string, mixed>
     */
    private static function hydrate(array $row): array
    {
        return [
            'id' => (string) $row['id'],
__HYDRATE_FIELDS__
        ];
    }
}
"""

_INTEGRATION_JWT_SIGNER = """
function signingKey(bool $valid): string
{
    if ($valid) {
        return trim((string) file_get_contents((string) getenv(__ENV_JWT_SECRET_FILE__)));
    }

    return WRONG_SECRET;
}

function signToken(string $signingInput, bool $valid): string
{
    return hash_hmac('sha256', $signingInput, signingKey($valid), true);
}

function tokenAlgorithm(bool $valid): string
{
    return 'HS256';
}
"""

# The harness provisions one OIDC private key and no second one, so the
# "wrong signature" case is signed with a different *algorithm* instead of a
# different RSA key. That still proves the token is refused, and it covers
# algorithm confusion -- an HS256 token offered to an RS256 verifier -- which
# a second RSA key would not have exercised.
_INTEGRATION_OIDC_SIGNER = """
function signToken(string $signingInput, bool $valid): string
{
    if (!$valid) {
        return hash_hmac('sha256', $signingInput, WRONG_SECRET, true);
    }
    $pem = (string) file_get_contents((string) getenv(__ENV_OIDC_PRIVATE_KEY_FILE__));
    $key = openssl_pkey_get_private($pem);
    if ($key === false) {
        throw new RuntimeException('OIDC_PRIVATE_KEY_UNUSABLE');
    }
    $signature = '';
    openssl_sign($signingInput, $signature, $key, OPENSSL_ALGO_SHA256);

    return $signature;
}

function tokenAlgorithm(bool $valid): string
{
    return $valid ? 'RS256' : 'HS256';
}
"""

_INTEGRATION_SOURCE = """
<?php

declare(strict_types=1);

/**
 * The ten-step scenario from production-contract.json, executed against the
 * PostgreSQL instance the runtime harness provisioned.
 *
 * This file is only run by the harness. `tests/run.php` stays offline and
 * database free, so a plain verification pass does not need a server.
 */

const WRONG_SECRET = 'an-entirely-different-secret-value-of-length';
const SAMPLE_BODY = __SAMPLE_BODY__;
const RECORD_ID = '6f1d9c52-4f0a-4c2e-9a58-6f4b2c8d1e70';
const COLLECTION_PATH = __COLLECTION_PATH__;

__SIGNER__
function base64UrlEncode(string $value): string
{
    return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
}

function token(?string $tenant, string $issuer, string $audience, bool $valid): string
{
    $header = base64UrlEncode((string) json_encode([
        'alg' => tokenAlgorithm($valid),
        'typ' => 'JWT',
    ]));
    $claims = [
        'iss' => $issuer,
        'aud' => $audience,
        'sub' => 'integration-subject',
        'iat' => time(),
        'exp' => time() + 300,
    ];
    if ($tenant !== null) {
        $claims[__TENANT_CLAIM__] = $tenant;
    }
    $body = base64UrlEncode((string) json_encode($claims));
    $signingInput = $header . '.' . $body;

    return $signingInput . '.' . base64UrlEncode(signToken($signingInput, $valid));
}

/**
 * A deliberately small HTTP/1.1 client. The scenario only ever talks to
 * 127.0.0.1, and the exact toolchain has no curl extension compiled in.
 *
 * @return array{0: int, 1: string}
 */
function send(string $method, string $path, ?string $bearer, ?string $body): array
{
    $port = getenv('PORT') ?: '__PORT__';
    $stream = @fsockopen('127.0.0.1', (int) $port, $errorCode, $errorMessage, 10);
    if ($stream === false) {
        throw new RuntimeException("CONNECT_FAILED:{$errorCode}:{$errorMessage}");
    }
    $request = "{$method} {$path} HTTP/1.1\\r\\nHost: 127.0.0.1\\r\\nConnection: close\\r\\n";
    if ($bearer !== null) {
        $request .= "Authorization: Bearer {$bearer}\\r\\n";
    }
    if ($body !== null) {
        $request .= "Content-Type: application/json\\r\\nContent-Length: " . strlen($body) . "\\r\\n\\r\\n" . $body;
    } else {
        $request .= "Content-Length: 0\\r\\n\\r\\n";
    }
    fwrite($stream, $request);
    $raw = '';
    while (!feof($stream)) {
        $raw .= fread($stream, 8192);
    }
    fclose($stream);
    $status = 0;
    if (preg_match('#^HTTP/1\\.[01] (\\d{3})#', $raw, $matches) === 1) {
        $status = (int) $matches[1];
    }
    $split = strpos($raw, "\\r\\n\\r\\n");

    return [$status, $split === false ? '' : substr($raw, $split + 4)];
}

$failures = 0;
function check(string $label, bool $condition, string $detail = ''): void
{
    global $failures;
    if ($condition) {
        printf("  ok   %s\\n", $label);

        return;
    }
    ++$failures;
    printf("  FAIL %s %s\\n", $label, $detail);
}

$issuer = (string) getenv(__ENV_AUTH_ISSUER__);
$audience = (string) getenv(__ENV_AUTH_AUDIENCE__);
$tenantA = token('tenant-a', $issuer, $audience, true);
$tenantB = token('tenant-b', $issuer, $audience, true);
$itemPath = COLLECTION_PATH . '/' . RECORD_ID;

check('health-unauthenticated', send('GET', '/health', null, null)[0] === 200);
check('missing-token-rejected', send('GET', COLLECTION_PATH, null, null)[0] === 401);
check(
    'bad-signature-rejected',
    send('GET', COLLECTION_PATH, token('tenant-a', $issuer, $audience, false), null)[0] === 401,
);
check(
    'wrong-audience-rejected',
    send('GET', COLLECTION_PATH, token('tenant-a', $issuer, 'another-service', true), null)[0] === 401,
);
check(
    'wrong-issuer-rejected',
    send('GET', COLLECTION_PATH, token('tenant-a', 'https://attacker.invalid/', $audience, true), null)[0] === 401,
);
check(
    'missing-tenant-claim-rejected',
    send('GET', COLLECTION_PATH, token(null, $issuer, $audience, true), null)[0] === 401,
);

[$createdStatus, $createdBody] = send('PUT', $itemPath, $tenantA, SAMPLE_BODY);
check('upsert-accepted', $createdStatus === 200, $createdBody);
[$readStatus, $readBody] = send('GET', $itemPath, $tenantA, null);
check('read-returns-record', $readStatus === 200 && str_contains($readBody, RECORD_ID), $readBody);
[$listStatus, $listBody] = send('GET', COLLECTION_PATH, $tenantA, null);
check('list-scoped-to-tenant', $listStatus === 200 && str_contains($listBody, RECORD_ID), $listBody);
check('cross-tenant-read-blocked', send('GET', $itemPath, $tenantB, null)[0] === 404);
check('cross-tenant-list-blocked', !str_contains(send('GET', COLLECTION_PATH, $tenantB, null)[1], RECORD_ID));
check('delete-removes-record', send('DELETE', $itemPath, $tenantA, null)[0] === 204);
check('deleted-record-is-gone', send('GET', $itemPath, $tenantA, null)[0] === 404);

if ($failures > 0) {
    printf("%d integration check(s) failed\\n", $failures);
    exit(1);
}
printf("all integration checks passed\\n");
"""

_OFFLINE_TEST_SOURCE = """
<?php

declare(strict_types=1);

namespace __NAMESPACE__;

// Both classes are required here so this file doubles as a parse check over
// the whole workspace: the repository's build analysis runs it, and `php -l`
// does not follow requires.
require __DIR__ . '/../src/TenantAuthenticator.php';
require __DIR__ . '/../src/__ENTITY__Store.php';

/**
 * Offline guards. These need neither a database nor key material, so the
 * standard verification pass stays hermetic.
 */
$failures = 0;
function assertTrue(string $label, bool $condition): void
{
    global $failures;
    if ($condition) {
        printf("  ok   %s\\n", $label);

        return;
    }
    ++$failures;
    printf("  FAIL %s\\n", $label);
}

foreach (__REQUIRED_EXTENSIONS__ as $extension) {
    assertTrue('extension-loaded:' . $extension, extension_loaded($extension));
}

try {
    TenantAuthenticator::requiredEnvironment('ELMOS_DEFINITELY_NOT_SET');
    assertTrue('required-environment-names-the-missing-variable', false);
} catch (\\RuntimeException $error) {
    assertTrue(
        'required-environment-names-the-missing-variable',
        str_contains($error->getMessage(), 'REQUIRED_ENVIRONMENT_MISSING'),
    );
}

$authenticator = new TenantAuthenticator();
assertTrue('null-authorization-is-refused', $authenticator->tenantFrom(null) === null);
assertTrue('non-bearer-authorization-is-refused', $authenticator->tenantFrom('Basic abc') === null);
assertTrue('malformed-token-is-refused', $authenticator->tenantFrom('Bearer not-a-jwt') === null);

if ($failures > 0) {
    printf("%d offline check(s) failed\\n", $failures);
    exit(1);
}
printf("all offline checks passed\\n");
"""


def _substitute(template: str, replacements: dict[str, str]) -> str:
    rendered = template.lstrip("\n")
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    leftovers = sorted(
        {
            fragment
            for fragment in rendered.split()
            if fragment.startswith("__") and fragment.endswith("__") and fragment != "__DIR__"
        }
    )
    if leftovers:
        raise ValueError("PHP_TEMPLATE_TOKEN_UNRESOLVED:" + ",".join(leftovers))
    return rendered


def _entity_type(request: SynthesisRequest) -> str:
    from .models import pascal

    return pascal(request.entities[0].singular)


def _security_source(request: SynthesisRequest) -> str:
    if request.auth_mode == "jwt":
        verify = _substitute(
            _SECURITY_JWT, {"__ENV_JWT_SECRET_FILE__": _php_literal(ENV_JWT_SECRET_FILE)}
        )
    else:
        verify = _substitute(
            _SECURITY_OIDC, {"__ENV_OIDC_JWKS_FILE__": _php_literal(ENV_OIDC_JWKS_FILE)}
        )
    return _substitute(
        _SECURITY_SOURCE,
        {
            "__NAMESPACE__": _php_namespace(request),
            "__VERIFY__": verify,
            "__TENANT_CLAIM__": _php_literal(TENANT_CLAIM),
            "__ENV_AUTH_ISSUER__": _php_literal(ENV_AUTH_ISSUER),
            "__ENV_AUTH_AUDIENCE__": _php_literal(ENV_AUTH_AUDIENCE),
        },
    )


def _php_namespace(request: SynthesisRequest) -> str:
    from .models import pascal

    return "\\".join(pascal(part) for part in request.namespace.split(".") if part)


def _store_source(request: SynthesisRequest, entity: EntitySpec) -> str:
    from .models import pascal

    sql = next(item for item in all_entity_sql(request, placeholder="?") if item.entity == entity.singular)
    hydrate = "\n".join(
        f"            {_php_literal(field.name)} => "
        f"{_cast_from_database(field, f'$row[{_php_literal(field.name)}]')},"
        for field in entity.fields
    )
    bind_values = ", ".join(_bind_value(field) for field in entity.fields)
    return _substitute(
        _STORE_SOURCE,
        {
            "__NAMESPACE__": _php_namespace(request),
            "__ENTITY__": pascal(entity.singular),
            "__LIST_SQL__": _php_literal(sql.list_sql),
            "__GET_SQL__": _php_literal(sql.get_sql),
            "__UPSERT_SQL__": _php_literal(sql.upsert_sql),
            "__DELETE_SQL__": _php_literal(sql.delete_sql),
            # Every SQL constant is produced whole in Python. Interpolating a
            # quoted literal into an already-quoted PHP string is how the
            # nested-quote parse error happens.
            "__BIND_TENANT_SQL__": _php_literal(
                f"SELECT set_config('{TENANT_SETTING}', ?, true)"
            ),
            "__TENANT_SETTING__": TENANT_SETTING,
            "__BIND_VALUES__": bind_values,
            "__HYDRATE_FIELDS__": hydrate,
        },
    )


def _index_source(request: SynthesisRequest) -> str:
    from .models import pascal

    requires = "\n".join(
        f"require __DIR__ . '/../src/{pascal(entity.singular)}Store.php';"
        for entity in request.entities
    )
    handlers: list[str] = []
    for entity in request.entities:
        entity_type = pascal(entity.singular)
        checks = [
            f"        if (!is_string($payload[{_php_literal(field.name)}] ?? null)\n"
            f"            || trim((string) $payload[{_php_literal(field.name)}]) === '') {{\n"
            f"            fail(422, 'PAYLOAD_INVALID');\n\n"
            f"            return;\n"
            f"        }}"
            for field in entity.fields
            if field.required and field.type == "string"
        ]
        required_checks = "\n".join(checks) or "        // no blank-string constraints declared"
        collection = f"/{entity.plural}"
        handlers.append(
            f"""
if ($path === {_php_literal(collection)} || str_starts_with($path, {_php_literal(collection + '/')})) {{
    $store = new {entity_type}Store($databaseUrl);
    if ($path === {_php_literal(collection)}) {{
        if ($method !== 'GET') {{
            fail(405, 'method_not_allowed');

            return;
        }}
        respond(200, ['items' => $store->list($tenant)]);

        return;
    }}
    $identifier = substr($path, {len(collection) + 1});
    if (preg_match(UUID_PATTERN, $identifier) !== 1) {{
        fail(422, 'RECORD_ID_MUST_BE_UUID');

        return;
    }}
    if ($method === 'GET') {{
        $record = $store->find($tenant, $identifier);
        if ($record === null) {{
            fail(404, 'not_found');

            return;
        }}
        respond(200, $record);

        return;
    }}
    if ($method === 'PUT') {{
        $payload = json_decode((string) file_get_contents('php://input'), true);
        if (!is_array($payload)) {{
            fail(422, 'PAYLOAD_INVALID');

            return;
        }}
{required_checks}
        respond(200, $store->save($tenant, $identifier, $payload));

        return;
    }}
    if ($method === 'DELETE') {{
        $store->delete($tenant, $identifier);
        http_response_code(204);

        return;
    }}
    fail(405, 'method_not_allowed');

    return;
}}
"""
        )
    body = "\n".join(handlers)
    return _substitute(
        """
<?php

declare(strict_types=1);

namespace __NAMESPACE__;

use RuntimeException;
use Throwable;

require __DIR__ . '/../src/TenantAuthenticator.php';
__REQUIRES__

const UUID_PATTERN = '/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/';

/** @param array<string, mixed> $body */
function respond(int $status, array $body): void
{
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
}

function fail(int $status, string $reason): void
{
    respond($status, ['error' => $reason]);
}

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

if ($path === '/health') {
    respond(200, ['status' => 'UP', 'service' => __SERVICE_NAME__]);

    return;
}

try {
    $authenticator = new TenantAuthenticator();
    $tenant = $authenticator->tenantFrom($_SERVER['HTTP_AUTHORIZATION'] ?? null);
    if ($tenant === null) {
        fail(401, 'unauthorized');

        return;
    }
    $reference = TenantAuthenticator::requiredEnvironment(__ENV_DATABASE_URL_FILE__);
    $databaseUrl = trim((string) file_get_contents($reference));
__HANDLERS__
    fail(404, 'not_found');
} catch (RuntimeException $error) {
    error_log('request failed: ' . $error->getMessage());
    fail(500, 'internal_error');
} catch (Throwable $error) {
    error_log('request failed: ' . $error->getMessage());
    fail(500, 'internal_error');
}
""",
        {
            "__NAMESPACE__": _php_namespace(request),
            "__REQUIRES__": requires,
            "__SERVICE_NAME__": _php_literal(request.project_name),
            "__ENV_DATABASE_URL_FILE__": _php_literal(ENV_DATABASE_URL_FILE),
            "__HANDLERS__": body,
        },
    )


def _integration_source(request: SynthesisRequest, port: int) -> str:
    entity = request.entities[0]
    body = json.dumps(
        {field.name: _sample_json(field) for field in entity.fields}, ensure_ascii=False
    )
    if request.auth_mode == "jwt":
        signer = _substitute(
            _INTEGRATION_JWT_SIGNER,
            {"__ENV_JWT_SECRET_FILE__": _php_literal(ENV_JWT_SECRET_FILE)},
        )
    else:
        signer = _substitute(
            _INTEGRATION_OIDC_SIGNER,
            {"__ENV_OIDC_PRIVATE_KEY_FILE__": _php_literal(ENV_OIDC_PRIVATE_KEY_FILE)},
        )
    return _substitute(
        _INTEGRATION_SOURCE,
        {
            "__SIGNER__": signer,
            "__SAMPLE_BODY__": _php_literal(body),
            "__COLLECTION_PATH__": _php_literal(f"/{entity.plural}"),
            "__TENANT_CLAIM__": _php_literal(TENANT_CLAIM),
            "__PORT__": str(port),
            "__ENV_AUTH_ISSUER__": _php_literal(ENV_AUTH_ISSUER),
            "__ENV_AUTH_AUDIENCE__": _php_literal(ENV_AUTH_AUDIENCE),
        },
    )


def render_php_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    from .models import pascal

    files = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "production-contract.json": pretty_json(production_contract(request)),
        "composer.json": pretty_json(
            {
                "name": f"elmos/{request.project_name}",
                "description": request.description,
                "type": "project",
                "license": "proprietary",
                "require": {
                    "php": f"=={PHP_VERSION}",
                    "ext-json": "*",
                    "ext-hash": "*",
                    "ext-pdo": "*",
                    "ext-pdo_pgsql": "*",
                    "ext-openssl": "*",
                },
                "autoload": {"psr-4": {f"{_php_namespace(request)}\\\\": "src/"}},
                "config": {"optimize-autoloader": True},
            }
        ),
        "src/TenantAuthenticator.php": _security_source(request),
        "public/index.php": _index_source(request),
        "tests/run.php": _substitute(
            _OFFLINE_TEST_SOURCE,
            {
                "__NAMESPACE__": _php_namespace(request),
                "__ENTITY__": pascal(request.entities[0].singular),
                "__REQUIRED_EXTENSIONS__": "["
                + ", ".join(_php_literal(name.lower()) for name in REQUIRED_EXTENSIONS)
                + "]",
            },
        ),
        "tests/integration.php": _integration_source(request, port),
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["php", "-S", f"127.0.0.1:{port}", "-t", "public", "public/index.php"],
            verify_command=["php", "tests/integration.php"],
            app_port_argument_index=2,
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {PHP_IMAGE}
            RUN docker-php-ext-install pdo pdo_pgsql
            WORKDIR /app
            COPY . .
            RUN addgroup -S app && adduser -S -G app -u 10001 app
            USER 10001:10001
            EXPOSE {port}
            HEALTHCHECK --interval=30s --timeout=3s CMD php -r "exit(@file_get_contents('http://127.0.0.1:{port}/health') ? 0 : 1);"
            ENTRYPOINT ["php", "-S", "0.0.0.0:{port}", "-t", "public", "public/index.php"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="php", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: php-production-ci
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
                  - run: php -l public/index.php
                  - run: php tests/run.php
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run
            test:
            \tphp -l public/index.php && php tests/run.php
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            """
        ),
        "README.md": target_readme(
            request,
            language=f"PHP {PHP_VERSION}",
            framework="PDO pgsql + built-in server",
            port=port,
            commands=(
                "php -l public/index.php\n"
                "php tests/run.php\n"
                "python3 scripts/local_runtime.py --verify"
            ),
        ),
    }
    for entity in request.entities:
        files[f"src/{pascal(entity.singular)}Store.php"] = _store_source(request, entity)
    return files
