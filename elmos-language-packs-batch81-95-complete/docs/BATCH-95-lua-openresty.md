# Batch 95: Lua / OpenResty / Embedded Scripting Pack

Generates and governs Lua applications, OpenResty gateways, embedded plugins, coroutine workflows, and sandboxed scripting.

## Skills

- PG391 `lua-project-discovery-and-inventory`
- PG392 `lua-parser-and-semantic-model`
- PG393 `openresty-nginx-application-profile`
- PG394 `lua-embedded-host-interop-generator`
- PG395 `lua-plugin-sandbox-capability-enforcer`
- PG396 `lua-coroutine-concurrency-modeler`
- PG397 `lua-resty-http-cache-gateway-generator`
- PG398 `lua-game-embedded-scripting-profile`
- PG399 `lua-package-build-config-generator`
- PG400 `lua-test-fuzz-generator`
- PG401 `lua-runtime-version-compatibility-checker`
- PG402 `lua-openresty-deployment-certifier`

## Safety boundary

Untrusted Lua and plugin execution must be capability-limited, resource-bounded, and isolated from secrets and host process authority.

## Principal risks

- sandbox escape
- event-loop blocking
- FFI memory error
- Lua/LuaJIT incompatibility
- shared-dictionary race
- untrusted plugin privilege
