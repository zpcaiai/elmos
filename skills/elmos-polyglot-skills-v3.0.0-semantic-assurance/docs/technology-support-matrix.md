# Technology Support Matrix

The package contains fourteen advertised technology entries. React and Flutter are framework adapters. Flutter internally requires Dart tooling.

| Technology | Kind | Preferred semantic source | Typical framework scope | Native gate |
|---|---|---|---|---|
| Java | language | Eclipse JDT, JavaParser | Spring Framework, Spring Boot, Jakarta EE, Quarkus | `mvn test` |
| Kotlin | language | Kotlin PSI, K2/FIR | Spring Boot, Ktor, Android, Jetpack Compose | `gradle test` |
| Python | language | CPython ast, LibCST | Django, FastAPI, Flask, Celery | `pytest` |
| C# | language | Roslyn, tree-sitter-c-sharp | ASP.NET MVC, ASP.NET Core, Entity Framework, Blazor | `dotnet build` |
| Go | language | go/ast, go/parser | net/http, Gin, Echo, Fiber | `go test ./...` |
| Rust | language | rust-analyzer, syn | Axum, Actix Web, Tokio, Tonic | `cargo check` |
| C++ | language | Clang AST, Clang LibTooling | STL, Boost, Qt, gRPC C++ | `cmake --build` |
| PHP | language | nikic/PHP-Parser, PHPStan parser | Laravel, Symfony, Slim, WordPress | `phpunit` |
| TypeScript | language | TypeScript Compiler API, ts-morph | NestJS, Next.js, Angular, React | `tsc --noEmit` |
| React | framework | TypeScript Compiler API, Babel | React, Next.js, React Router, Redux | `vitest` |
| Objective-C | language | Clang AST, libclang | Foundation, UIKit, AppKit, Core Data | `xcodebuild test` |
| Swift | language | SwiftSyntax, SourceKit-LSP | SwiftUI, UIKit, Vapor, Combine | `swift test` |
| Flutter | framework | Dart analyzer, analyzer package | Flutter, Material, Cupertino, Riverpod | `flutter analyze` |
| JavaScript | language | Babel, SWC | Node.js, Express, Fastify, React | `node --test` |

## Support states

- **planned**: a route can be represented through shared IR, but no route-specific executed evidence exists.
- **reference**: a route profile and route-specific acceptance plan exist.
- **implemented**: production code, native builds, and required tests exist for a bounded scope.
- **verified**: current evidence satisfies the route's declared verification profile.
- **certified**: a bounded readiness certificate exists for exact artifacts and environment.

This bundle ships at `not-run`. It does not mark any route implemented, verified, or certified.

## Pairwise route count

Fourteen entries create 196 matrix cells: 14 same-stack modernization cells and 182 directed cross-technology cells. The full matrix is in `route-matrix.csv`.
