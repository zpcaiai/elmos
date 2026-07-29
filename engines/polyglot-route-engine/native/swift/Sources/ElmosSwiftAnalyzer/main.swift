// Lifts one named Swift function into the engine's semantic IR, using
// SwiftSyntax -- the same parser the compiler itself uses -- and printing the
// identical JSON contract the JDK, Roslyn, CPython and clang analyzers print.
//
// Usage: ElmosSwiftAnalyzer <source> <function>
//
// The certified `typed-pure-function-v1` subset accepted here:
//
//   types        Int / Int8 / Int16 / Int32 / Int64 -> integer
//                Double                             -> number
//                Bool                               -> boolean
//                String                             -> string
//   statements   `return`, `if` / `else` (with braced bodies)
//   expressions  identifiers, Int/Double/Bool/String literals, parentheses,
//                and the binary operators + - * / % < <= > >= == != && ||
//
// Everything else fails closed with a `SWIFT_*` reason, in the same shape the
// other analyzers use. Three refusals are deliberate rather than incidental:
//
//   * `Float` -- a 24-bit significand does not round-trip through the
//     canonical `number` (binary64), exactly as in the Java, C#, C++ and
//     Objective-C analyzers.
//   * `UInt`/`UInt64`/... -- the canonical integer is signed 64-bit, and the
//     upper half of an unsigned 64-bit range has no representation in it.
//   * any optional (`Int?`) -- the subset has no null, so a nullable
//     parameter cannot be carried across a route.
//
// Swift's `/` and `%` truncate toward zero and `String` compares by value, so
// no operator is rewritten on the way in or out; see the engine README.

import Foundation
import SwiftParser
import SwiftParserDiagnostics
import SwiftSyntax

/// Must match the `exact:` pin in Package.swift. It is reported as
/// `analyzer_version` in the emitted IR, which is what the engine records as
/// the evidence of *which* frontend produced a route.
let swiftSyntaxVersion = "600.0.1"

// MARK: - JSON

/// A minimal, order-preserving JSON writer. Hand-rolled for the same reason
/// `Analyzer.java` hand-rolls one: the output contract is a fixed, tiny shape,
/// and key order stays readable in the emitted artifacts.
indirect enum JSONValue {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([(String, JSONValue)])

    var encoded: String {
        switch self {
        case .string(let value):
            return JSONValue.quote(value)
        case .int(let value):
            return String(value)
        case .double(let value):
            return String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .array(let items):
            return "[" + items.map { $0.encoded }.joined(separator: ",") + "]"
        case .object(let entries):
            let body = entries.map { JSONValue.quote($0.0) + ":" + $0.1.encoded }
            return "{" + body.joined(separator: ",") + "}"
        }
    }

    static func quote(_ value: String) -> String {
        var result = "\""
        for character in value.unicodeScalars {
            switch character {
            case "\"": result += "\\\""
            case "\\": result += "\\\\"
            case "\n": result += "\\n"
            case "\r": result += "\\r"
            case "\t": result += "\\t"
            default:
                if character.value < 0x20 {
                    result += String(format: "\\u%04x", character.value)
                } else {
                    result.unicodeScalars.append(character)
                }
            }
        }
        return result + "\""
    }
}

struct AnalyzerError: Error {
    let reason: String
    init(_ reason: String) { self.reason = reason }
}

// MARK: - Types

func canonicalType(_ syntax: TypeSyntax?) throws -> String {
    guard let syntax else { throw AnalyzerError("SWIFT_EXPLICIT_TYPE_REQUIRED") }
    let text = syntax.trimmedDescription
    switch text {
    case "Int", "Int8", "Int16", "Int32", "Int64":
        // Narrower widths widen to the canonical signed 64-bit integer
        // exactly; only fixed-width overflow behaviour differs, the same
        // documented boundary the Java/C#/C++ analyzers carry.
        return "integer"
    case "Double":
        return "number"
    case "Bool":
        return "boolean"
    case "String":
        return "string"
    case "Float", "Float16", "Float80", "CGFloat":
        throw AnalyzerError("SWIFT_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:\(text)")
    case "UInt", "UInt8", "UInt16", "UInt32", "UInt64":
        throw AnalyzerError("SWIFT_UNSIGNED_TYPE_OUTSIDE_CERTIFIED_SUBSET:\(text)")
    case "Decimal":
        throw AnalyzerError("SWIFT_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET:\(text)")
    default:
        if text.hasSuffix("?") || text.hasSuffix("!") || syntax.is(OptionalTypeSyntax.self) {
            throw AnalyzerError("SWIFT_OPTIONAL_TYPE_OUTSIDE_CERTIFIED_SUBSET:\(text)")
        }
        throw AnalyzerError("SWIFT_UNSUPPORTED_TYPE:\(text)")
    }
}

// MARK: - Expressions

let supportedOperators: Set<String> = [
    "+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||",
]

func unwrap(_ expression: ExprSyntax) -> ExprSyntax {
    // `(a + b)` parses as a single-element tuple with no label.
    if let tuple = expression.as(TupleExprSyntax.self),
        tuple.elements.count == 1,
        let only = tuple.elements.first,
        only.label == nil
    {
        return unwrap(only.expression)
    }
    return expression
}

func liftExpression(_ raw: ExprSyntax) throws -> JSONValue {
    let expression = unwrap(raw)

    if let reference = expression.as(DeclReferenceExprSyntax.self) {
        return .object([
            ("kind", .string("name")),
            ("value", .string(reference.baseName.text)),
        ])
    }

    if let literal = expression.as(IntegerLiteralExprSyntax.self) {
        let text = literal.literal.text.replacingOccurrences(of: "_", with: "")
        guard let value = Int(text) else {
            throw AnalyzerError("SWIFT_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE:\(text)")
        }
        return .object([("kind", .string("literal")), ("value", .int(value))])
    }

    if let literal = expression.as(FloatLiteralExprSyntax.self) {
        let text = literal.literal.text.replacingOccurrences(of: "_", with: "")
        guard let value = Double(text), value.isFinite else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_FLOAT_LITERAL:\(text)")
        }
        return .object([("kind", .string("literal")), ("value", .double(value))])
    }

    if let literal = expression.as(BooleanLiteralExprSyntax.self) {
        let value = literal.literal.tokenKind == .keyword(.true)
        return .object([("kind", .string("literal")), ("value", .bool(value))])
    }

    if let literal = expression.as(StringLiteralExprSyntax.self) {
        // Only a plain, non-interpolated literal: interpolation is a call
        // into arbitrary code, which is outside the pure-function subset.
        guard literal.segments.count == 1,
            let segment = literal.segments.first?.as(StringSegmentSyntax.self)
        else {
            throw AnalyzerError("SWIFT_STRING_INTERPOLATION_OUTSIDE_CERTIFIED_SUBSET")
        }
        return .object([
            ("kind", .string("literal")),
            ("value", .string(segment.content.text)),
        ])
    }

    if let infix = expression.as(InfixOperatorExprSyntax.self) {
        guard let operatorToken = infix.operator.as(BinaryOperatorExprSyntax.self) else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_OPERATOR:\(infix.operator.trimmedDescription)")
        }
        let symbol = operatorToken.operator.text
        guard supportedOperators.contains(symbol) else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_OPERATOR:\(symbol)")
        }
        return .object([
            ("kind", .string("binary")),
            ("operator", .string(symbol)),
            ("left", try liftExpression(infix.leftOperand)),
            ("right", try liftExpression(infix.rightOperand)),
        ])
    }

    throw AnalyzerError("SWIFT_UNSUPPORTED_EXPRESSION:\(expression.kind)")
}

// MARK: - Statements

func liftStatements(_ statements: CodeBlockItemListSyntax) throws -> [JSONValue] {
    var result: [JSONValue] = []
    for item in statements {
        if let returnStatement = item.item.as(ReturnStmtSyntax.self) {
            guard let value = returnStatement.expression else {
                throw AnalyzerError("SWIFT_RETURN_WITHOUT_VALUE")
            }
            result.append(
                .object([
                    ("kind", .string("return")),
                    ("expression", try liftExpression(value)),
                ])
            )
            continue
        }
        if let conditional = item.item.as(ExpressionStmtSyntax.self)?
            .expression.as(IfExprSyntax.self)
        {
            result.append(try liftIf(conditional))
            continue
        }
        if let conditional = item.item.as(IfExprSyntax.self) {
            result.append(try liftIf(conditional))
            continue
        }
        throw AnalyzerError("SWIFT_UNSUPPORTED_STATEMENT:\(item.item.kind)")
    }
    return result
}

func liftIf(_ conditional: IfExprSyntax) throws -> JSONValue {
    // `if let` / `if case` / `if #available` bind, destructure or query the
    // platform; the subset has no canonical form for any of them, so only a
    // single plain boolean expression is accepted.
    guard conditional.conditions.count == 1,
        let element = conditional.conditions.first
    else {
        throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION")
    }
    guard case .expression(let condition) = element.condition else {
        throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION:\(element.condition.kind)")
    }
    var elseBody: [JSONValue] = []
    if let elseBlock = conditional.elseBody {
        switch elseBlock {
        case .codeBlock(let block):
            elseBody = try liftStatements(block.statements)
        case .ifExpr(let chained):
            // `else if` is one nested if statement.
            elseBody = [try liftIf(chained)]
        }
    }
    return .object([
        ("kind", .string("if")),
        ("condition", try liftExpression(condition)),
        ("then", .array(try liftStatements(conditional.body.statements))),
        ("else", .array(elseBody)),
    ])
}

// MARK: - Functions

func liftFunction(_ declaration: FunctionDeclSyntax) throws -> JSONValue {
    guard let body = declaration.body else {
        throw AnalyzerError("SWIFT_FUNCTION_BODY_REQUIRED")
    }
    if declaration.signature.effectSpecifiers?.asyncSpecifier != nil {
        throw AnalyzerError("ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    }
    if declaration.signature.effectSpecifiers?.throwsClause != nil {
        throw AnalyzerError("SWIFT_THROWING_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    }
    if declaration.genericParameterClause != nil {
        throw AnalyzerError("SWIFT_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    }

    var parameters: [JSONValue] = []
    for parameter in declaration.signature.parameterClause.parameters {
        // `func f(_ value: Int)` -> the binding name is `value`; with a label
        // (`func f(of value: Int)`) it is the second name.
        let name = (parameter.secondName ?? parameter.firstName).text
        guard name != "_" else { throw AnalyzerError("SWIFT_PARAMETER_NAME_REQUIRED") }
        if parameter.defaultValue != nil {
            throw AnalyzerError("SWIFT_DEFAULT_ARGUMENT_OUTSIDE_CERTIFIED_SUBSET")
        }
        parameters.append(
            .object([
                ("name", .string(name)),
                ("type", .string(try canonicalType(parameter.type))),
            ])
        )
    }

    guard let returnClause = declaration.signature.returnClause else {
        throw AnalyzerError("SWIFT_EXPLICIT_RETURN_TYPE_REQUIRED")
    }

    return .object([
        ("name", .string(declaration.name.text)),
        ("parameters", .array(parameters)),
        ("return_type", .string(try canonicalType(returnClause.type))),
        ("body", .array(try liftStatements(body.statements))),
    ])
}

// MARK: - Entry point

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    FileHandle.standardError.write(
        Data("usage: ElmosSwiftAnalyzer <source> <function>\n".utf8)
    )
    exit(2)
}

let sourcePath = URL(fileURLWithPath: arguments[1]).standardizedFileURL
let functionName = arguments[2]

do {
    let source = try String(contentsOf: sourcePath, encoding: .utf8)
    let tree = Parser.parse(source: source)

    // Parser diagnostics are carried, not swallowed: a source that does not
    // parse cleanly blocks emission downstream, exactly as in Analyzer.java.
    let converter = SourceLocationConverter(
        fileName: sourcePath.lastPathComponent, tree: tree)
    let diagnostics = ParseDiagnosticsGenerator.diagnostics(for: tree)
        .filter { $0.diagMessage.severity == .error }
        .map { diagnostic -> String in
            let line = converter.location(for: diagnostic.position).line
            return "\(diagnostic.diagMessage.diagnosticID.id):\(line)"
        }
        .sorted()

    var functions: [JSONValue] = []
    var failures: [String] = []
    for statement in tree.statements {
        guard let declaration = statement.item.as(FunctionDeclSyntax.self),
            declaration.name.text == functionName
        else { continue }
        do {
            functions.append(try liftFunction(declaration))
        } catch let error as AnalyzerError {
            failures.append(error.reason)
        }
    }

    if let failure = failures.first, functions.isEmpty {
        FileHandle.standardError.write(Data((failure + "\n").utf8))
        exit(1)
    }

    var reasons = diagnostics
    if functions.isEmpty { reasons.append("FUNCTION_NOT_FOUND:\(functionName)") }

    let output = JSONValue.object([
        ("schema_version", .string("1.0.0")),
        ("source_language", .string("swift")),
        ("source_file", .string(sourcePath.lastPathComponent)),
        ("analyzer", .string("SwiftSyntax")),
        ("analyzer_version", .string(swiftSyntaxVersion)),
        ("functions", .array(functions)),
        ("diagnostics", .array(reasons.map { JSONValue.string($0) })),
    ])
    print(output.encoded)
} catch let error as AnalyzerError {
    FileHandle.standardError.write(Data((error.reason + "\n").utf8))
    exit(1)
} catch {
    FileHandle.standardError.write(Data(("SWIFT_ANALYZER_FAILED:\(error)\n").utf8))
    exit(1)
}
