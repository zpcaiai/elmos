// swift-tools-version: 5.9
//
// The Swift half of the polyglot route engine's analyzer set, mirroring the
// Roslyn CLI in `engines/dotnet-engine` and the TypeScript Compiler API CLI in
// `engines/frontend-client-engine`: a real compiler frontend that prints the
// same semantic IR JSON, never a text-level parse.
//
// PIN: swift-syntax's major version tracks the Swift release it ships with
// (5.10 -> 510.x, 6.0 -> 600.x, and so on). It is pinned exactly here, and a
// pin that does not match the host toolchain fails the build loudly rather
// than resolving to "whatever is newest" -- the same posture as
// ELMOS_SWIFT_VERSION in `toolchains.py`. Change this one line to the major
// matching `swiftc --version` on the host, and record that pairing in the
// engine README.
import PackageDescription

let package = Package(
    name: "ElmosSwiftAnalyzer",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-syntax.git", exact: "600.0.1")
    ],
    targets: [
        .executableTarget(
            name: "ElmosSwiftAnalyzer",
            dependencies: [
                .product(name: "SwiftSyntax", package: "swift-syntax"),
                .product(name: "SwiftParser", package: "swift-syntax"),
                .product(name: "SwiftParserDiagnostics", package: "swift-syntax"),
                .product(name: "SwiftOperators", package: "swift-syntax"),
            ]
        )
    ]
)
