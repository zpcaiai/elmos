// Lifts one named Swift function into the engine's semantic IR, using
// SwiftSyntax -- the same parser the compiler itself uses -- and printing the
// identical JSON contract the JDK, Roslyn, CPython and clang analyzers print.
//
// Usage: ElmosSwiftAnalyzer <source> <function> [--emitted-target]
//
// The certified `typed-pure-function-v1` subset accepted here:
//
//   types        Int64                              -> integer
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
import SwiftOperators
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

struct LiftContext {
    let sourceFile: String
    let emittedTarget: Bool
    var environment: [String: String]
    var mutableVariables: Set<String>
    var parameterNames: Set<String>
    var loopVariables: Set<String>
    var inLoop: Bool
}

func compileTimeInt64(_ raw: ExprSyntax) -> Int64? {
    let expr = unwrap(raw)
    if let lit = expr.as(IntegerLiteralExprSyntax.self) {
        let text = lit.literal.text.replacingOccurrences(of: "_", with: "")
        return Int64(text)
    }
    if let prefix = expr.as(PrefixOperatorExprSyntax.self),
        prefix.operator.text == "-",
        let lit = prefix.expression.as(IntegerLiteralExprSyntax.self)
    {
        let text = lit.literal.text.replacingOccurrences(of: "_", with: "")
        if let val = Int64(text) {
            return -val
        }
    }
    return nil
}

func sourceSpan<T: SyntaxProtocol>(_ syntax: T, _ context: LiftContext) throws -> JSONValue {
    let start = syntax.positionAfterSkippingLeadingTrivia.utf8Offset
    let end = syntax.endPositionBeforeTrailingTrivia.utf8Offset
    guard start >= 0, end > start else {
        throw AnalyzerError("SWIFT_SOURCE_SPAN_INVALID")
    }
    return .object([
        ("file", .string(context.sourceFile)),
        ("start_byte", .int(start)),
        ("end_byte", .int(end)),
    ])
}

func spanned<T: SyntaxProtocol>(
    _ entries: [(String, JSONValue)], _ syntax: T, _ context: LiftContext
) throws -> JSONValue {
    return .object(entries + [("source_span", try sourceSpan(syntax, context))])
}

func replacingSpan<T: SyntaxProtocol>(
    _ value: JSONValue, _ syntax: T, _ context: LiftContext
) throws -> JSONValue {
    guard case .object(let entries) = value else {
        throw AnalyzerError("SWIFT_EXPRESSION_OBJECT_REQUIRED")
    }
    return try spanned(entries.filter { $0.0 != "source_span" }, syntax, context)
}

// MARK: - Types

func canonicalType(_ syntax: TypeSyntax?) throws -> String {
    guard let syntax else { throw AnalyzerError("SWIFT_EXPLICIT_TYPE_REQUIRED") }
    let text = syntax.trimmedDescription
    switch text {
    case "Int64":
        return "integer"
    case "Int", "Int8", "Int16", "Int32":
        throw AnalyzerError("SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:\(text)")
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

func inferredType(_ raw: ExprSyntax, _ context: LiftContext) throws -> String {
    let expression = unwrap(raw)
    if let reference = expression.as(DeclReferenceExprSyntax.self) {
        if let type = context.environment[reference.baseName.text] {
            return type
        }
        throw AnalyzerError("SWIFT_UNDECLARED_VARIABLE:\(reference.baseName.text)")
    }
    if expression.is(IntegerLiteralExprSyntax.self) {
        return "integer"
    }
    if let prefix = expression.as(PrefixOperatorExprSyntax.self) {
        if prefix.operator.text == "-" { return "integer" }
        if prefix.operator.text == "!" { return "boolean" }
    }
    if expression.is(FloatLiteralExprSyntax.self) { return "number" }
    if expression.is(BooleanLiteralExprSyntax.self) { return "boolean" }
    if expression.is(StringLiteralExprSyntax.self) { return "string" }
    if let call = expression.as(FunctionCallExprSyntax.self),
        let callee = call.calledExpression.as(DeclReferenceExprSyntax.self)
    {
        if context.emittedTarget && callee.baseName.text == "Int64" { return "integer" }
        if context.emittedTarget && callee.baseName.text == "Double" { return "number" }
        if context.emittedTarget && callee.baseName.text == "elmosNonZero" { return "number" }
    }
    if let member = expression.as(MemberAccessExprSyntax.self),
        let base = member.base?.as(DeclReferenceExprSyntax.self),
        context.emittedTarget && base.baseName.text == "Int64"
    {
        return "integer"
    }
    if let infix = expression.as(InfixOperatorExprSyntax.self),
        let operatorToken = infix.operator.as(BinaryOperatorExprSyntax.self)
    {
        let symbol = operatorToken.operator.text
        if ["<", "<=", ">", ">=", "==", "!=", "&&", "||"].contains(symbol) {
            return "boolean"
        }
        let left = try inferredType(infix.leftOperand, context)
        let right = try inferredType(infix.rightOperand, context)
        if left == right { return left }
    }
    throw AnalyzerError("SWIFT_EXPRESSION_TYPE_UNRESOLVED:\(expression.kind)")
}

func liftExpression(_ raw: ExprSyntax, _ context: LiftContext) throws -> JSONValue {
    let expression = unwrap(raw)

    if let reference = expression.as(DeclReferenceExprSyntax.self) {
        return try spanned([
            ("kind", .string("name")),
            ("value", .string(reference.baseName.text)),
        ], raw, context)
    }

    if let literal = expression.as(IntegerLiteralExprSyntax.self) {
        let text = literal.literal.text.replacingOccurrences(of: "_", with: "")
        guard let value = Int64(text) else {
            throw AnalyzerError("SWIFT_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE:\(text)")
        }
        return try spanned(
            [("kind", .string("literal")), ("value", .int(Int(value)))], raw, context)
    }

    if let prefix = expression.as(PrefixOperatorExprSyntax.self),
        prefix.operator.text == "-",
        let literal = prefix.expression.as(IntegerLiteralExprSyntax.self)
    {
        let digits = literal.literal.text.replacingOccurrences(of: "_", with: "")
        guard let value = Int64("-" + digits) else {
            throw AnalyzerError("SWIFT_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE:-\(digits)")
        }
        return try spanned(
            [("kind", .string("literal")), ("value", .int(Int(value)))], raw, context)
    }

    if let literal = expression.as(FloatLiteralExprSyntax.self) {
        let text = literal.literal.text.replacingOccurrences(of: "_", with: "")
        guard let value = Double(text), value.isFinite else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_FLOAT_LITERAL:\(text)")
        }
        return try spanned(
            [("kind", .string("literal")), ("value", .double(value))], raw, context)
    }

    if let literal = expression.as(BooleanLiteralExprSyntax.self) {
        let value = literal.literal.tokenKind == .keyword(.true)
        return try spanned(
            [("kind", .string("literal")), ("value", .bool(value))], raw, context)
    }

    if let literal = expression.as(StringLiteralExprSyntax.self) {
        // Only a plain, non-interpolated literal: interpolation is a call
        // into arbitrary code, which is outside the pure-function subset.
        guard literal.segments.count == 1,
            let segment = literal.segments.first?.as(StringSegmentSyntax.self)
        else {
            throw AnalyzerError("SWIFT_STRING_INTERPOLATION_OUTSIDE_CERTIFIED_SUBSET")
        }
        return try spanned([
            ("kind", .string("literal")),
            ("value", .string(segment.content.text)),
        ], raw, context)
    }

    if let call = expression.as(FunctionCallExprSyntax.self) {
        guard context.emittedTarget,
            let callee = call.calledExpression.as(DeclReferenceExprSyntax.self)
        else {
            throw AnalyzerError("SWIFT_CALL_OUTSIDE_CERTIFIED_SUBSET")
        }
        if callee.baseName.text == "Int64" {
            guard call.arguments.count == 1,
                let argument = call.arguments.first,
                argument.label == nil,
                argument.expression.is(IntegerLiteralExprSyntax.self)
                    || argument.expression.is(PrefixOperatorExprSyntax.self)
            else {
                throw AnalyzerError("SWIFT_EMITTED_INT64_LITERAL_INVALID")
            }
            return try replacingSpan(
                try liftExpression(argument.expression, context), raw, context)
        }
        if callee.baseName.text == "Double" {
            guard call.arguments.count == 1,
                let argument = call.arguments.first,
                argument.label == nil
            else {
                throw AnalyzerError("SWIFT_EMITTED_DOUBLE_LITERAL_INVALID")
            }
            return try replacingSpan(
                try liftExpression(argument.expression, context), raw, context)
        }
        guard callee.baseName.text == "elmosNonZero" else {
            throw AnalyzerError("SWIFT_EMITTED_HELPER_UNRECOGNIZED:\(callee.baseName.text)")
        }
        guard call.arguments.count == 1,
            let argument = call.arguments.first,
            argument.label == nil
        else {
            throw AnalyzerError("SWIFT_EMITTED_HELPER_ARITY:elmosNonZero")
        }
        return try replacingSpan(
            try liftExpression(argument.expression, context), raw, context)
    }

    if context.emittedTarget,
        let member = expression.as(MemberAccessExprSyntax.self),
        let base = member.base?.as(DeclReferenceExprSyntax.self),
        base.baseName.text == "Int64",
        member.declName.baseName.text == "min" || member.declName.baseName.text == "max"
    {
        let value = member.declName.baseName.text == "min" ? Int64.min : Int64.max
        return try spanned(
            [("kind", .string("literal")), ("value", .int(Int(value)))], raw, context)
    }

    if let infix = expression.as(InfixOperatorExprSyntax.self) {
        guard let operatorToken = infix.operator.as(BinaryOperatorExprSyntax.self) else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_OPERATOR:\(infix.operator.trimmedDescription)")
        }
        let symbol = operatorToken.operator.text
        guard supportedOperators.contains(symbol) else {
            throw AnalyzerError("SWIFT_UNSUPPORTED_OPERATOR:\(symbol)")
        }
        if context.emittedTarget && symbol == "/",
            try inferredType(infix.leftOperand, context) == "number"
        {
            let right = unwrap(infix.rightOperand)
            guard let call = right.as(FunctionCallExprSyntax.self),
                let callee = call.calledExpression.as(DeclReferenceExprSyntax.self),
                callee.baseName.text == "elmosNonZero"
            else {
                throw AnalyzerError("SWIFT_EMITTED_FLOAT_DIVISOR_WITHOUT_EXACT_HELPER")
            }
        }
        return try spanned([
            ("kind", .string("binary")),
            ("operator", .string(symbol)),
            ("left", try liftExpression(infix.leftOperand, context)),
            ("right", try liftExpression(infix.rightOperand, context)),
        ], raw, context)
    }

    throw AnalyzerError("SWIFT_UNSUPPORTED_EXPRESSION:\(expression.kind)")
}

// MARK: - Statements

func liftStatements(
    _ statements: CodeBlockItemListSyntax, _ context: inout LiftContext
) throws -> [JSONValue] {
    var result: [JSONValue] = []
    for item in statements {
        if item.item.is(LabeledStmtSyntax.self) {
            throw AnalyzerError("SWIFT_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET")
        }

        if let returnStatement = item.item.as(ReturnStmtSyntax.self) {
            guard let value = returnStatement.expression else {
                throw AnalyzerError("SWIFT_RETURN_WITHOUT_VALUE")
            }
            result.append(
                try spanned([
                    ("kind", .string("return")),
                    ("expression", try liftExpression(value, context)),
                ], returnStatement, context)
            )
            continue
        }

        if item.item.is(RepeatWhileStmtSyntax.self) {
            throw AnalyzerError("SWIFT_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET")
        }

        if let whileStmt = item.item.as(WhileStmtSyntax.self) {
            guard whileStmt.conditions.count == 1,
                let element = whileStmt.conditions.first
            else {
                throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION")
            }
            guard case .expression(let rawCondition) = element.condition else {
                throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION:\(element.condition.kind)")
            }
            let condition = unwrap(rawCondition)
            let condType = try inferredType(condition, context)
            guard condType == "boolean" else {
                throw AnalyzerError("SWIFT_CONDITION_MUST_BE_BOOLEAN")
            }
            let liftedCond = try liftExpression(condition, context)
            var loopContext = context
            loopContext.inLoop = true
            let bodyStatements = try liftStatements(whileStmt.body.statements, &loopContext)
            result.append(
                try spanned([
                    ("kind", .string("while")),
                    ("condition", liftedCond),
                    ("body", .array(bodyStatements)),
                ], whileStmt, context)
            )
            continue
        }

        if let forStmt = item.item.as(ForStmtSyntax.self) {
            guard let identifier = forStmt.pattern.as(IdentifierPatternSyntax.self) else {
                throw AnalyzerError("SWIFT_FOR_VARIABLE_REQUIRED")
            }
            let loopVar = identifier.identifier.text
            guard loopVar != "_" else {
                throw AnalyzerError("SWIFT_FOR_VARIABLE_REQUIRED")
            }

            let startExpr: ExprSyntax
            let endExpr: ExprSyntax
            let stepExpr: ExprSyntax?

            let sequence = unwrap(forStmt.sequence)
            if let infix = sequence.as(InfixOperatorExprSyntax.self),
                let binOp = infix.operator.as(BinaryOperatorExprSyntax.self)
            {
                let opText = binOp.operator.text
                if opText == "..." {
                    throw AnalyzerError("SWIFT_FOR_CLOSED_RANGE_REJECTED")
                }
                guard opText == "..<" else {
                    throw AnalyzerError("SWIFT_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET")
                }
                startExpr = infix.leftOperand
                endExpr = infix.rightOperand
                stepExpr = nil
            } else if let call = sequence.as(FunctionCallExprSyntax.self),
                let callee = call.calledExpression.as(DeclReferenceExprSyntax.self),
                callee.baseName.text == "stride"
            {
                var fromArg: ExprSyntax? = nil
                var toArg: ExprSyntax? = nil
                var byArg: ExprSyntax? = nil
                for arg in call.arguments {
                    if let label = arg.label?.text {
                        if label == "from" {
                            fromArg = arg.expression
                        } else if label == "to" {
                            toArg = arg.expression
                        } else if label == "through" {
                            throw AnalyzerError("SWIFT_FOR_CLOSED_RANGE_REJECTED")
                        } else if label == "by" {
                            byArg = arg.expression
                        }
                    }
                }
                guard let f = fromArg, let t = toArg, let b = byArg else {
                    throw AnalyzerError("SWIFT_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET")
                }
                startExpr = f
                endExpr = t
                stepExpr = b
            } else {
                throw AnalyzerError("SWIFT_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET")
            }

            guard try inferredType(startExpr, context) == "integer" else {
                throw AnalyzerError("SWIFT_FOR_VARIABLE_TYPE_UNSUPPORTED")
            }
            guard try inferredType(endExpr, context) == "integer" else {
                throw AnalyzerError("SWIFT_FOR_VARIABLE_TYPE_UNSUPPORTED")
            }
            if let step = stepExpr {
                guard try inferredType(step, context) == "integer" else {
                    throw AnalyzerError("SWIFT_FOR_VARIABLE_TYPE_UNSUPPORTED")
                }
                if let stepVal = compileTimeInt64(step) {
                    if stepVal < 0 {
                        throw AnalyzerError("SWIFT_FOR_DOWNTO_REJECTED")
                    }
                    if stepVal == 0 {
                        throw AnalyzerError("SWIFT_FOR_NON_POSITIVE_STEP_REJECTED")
                    }
                }
            }

            if let startVal = compileTimeInt64(startExpr), let endVal = compileTimeInt64(endExpr) {
                let stepVal = stepExpr.flatMap(compileTimeInt64) ?? 1
                if stepVal > 0 && startVal >= endVal {
                    throw AnalyzerError("SWIFT_FOR_CONDITION_NON_MONOTONIC")
                }
            }

            var loopContext = context
            loopContext.inLoop = true
            loopContext.environment[loopVar] = "integer"
            loopContext.loopVariables.insert(loopVar)

            let bodyStatements = try liftStatements(forStmt.body.statements, &loopContext)

            var entries: [(String, JSONValue)] = [
                ("kind", .string("for")),
                ("name", .string(loopVar)),
                ("type", .string("integer")),
                ("start", try liftExpression(startExpr, context)),
                ("end", try liftExpression(endExpr, context)),
            ]
            if let step = stepExpr {
                entries.append(("step", try liftExpression(step, context)))
            }
            entries.append(("body", .array(bodyStatements)))
            result.append(try spanned(entries, forStmt, context))
            continue
        }

        if let breakStmt = item.item.as(BreakStmtSyntax.self) {
            guard context.inLoop else {
                throw AnalyzerError("SWIFT_BREAK_OUTSIDE_LOOP")
            }
            if breakStmt.label != nil {
                throw AnalyzerError("SWIFT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET")
            }
            result.append(
                try spanned([
                    ("kind", .string("break")),
                ], breakStmt, context)
            )
            continue
        }

        if let continueStmt = item.item.as(ContinueStmtSyntax.self) {
            guard context.inLoop else {
                throw AnalyzerError("SWIFT_CONTINUE_OUTSIDE_LOOP")
            }
            if continueStmt.label != nil {
                throw AnalyzerError("SWIFT_LABELED_CONTINUE_OUTSIDE_CERTIFIED_SUBSET")
            }
            result.append(
                try spanned([
                    ("kind", .string("continue")),
                ], continueStmt, context)
            )
            continue
        }

        if let varDecl = item.item.as(VariableDeclSyntax.self) {
            let isVar = varDecl.bindingSpecifier.tokenKind == .keyword(.var)
            let isLet = varDecl.bindingSpecifier.tokenKind == .keyword(.let)
            guard isVar || isLet else {
                throw AnalyzerError("SWIFT_UNSUPPORTED_VARIABLE_DECLARATION")
            }
            for binding in varDecl.bindings {
                guard let identifier = binding.pattern.as(IdentifierPatternSyntax.self) else {
                    throw AnalyzerError("SWIFT_UNSUPPORTED_PATTERN:\(binding.pattern.kind)")
                }
                let varName = identifier.identifier.text
                guard let typeSyntax = binding.typeAnnotation?.type else {
                    throw AnalyzerError("SWIFT_EXPLICIT_TYPE_REQUIRED")
                }
                let declaredType = try canonicalType(typeSyntax)
                guard let initializer = binding.initializer else {
                    throw AnalyzerError("SWIFT_LOCAL_INITIALIZER_REQUIRED")
                }
                let initType = try inferredType(initializer.value, context)
                guard initType == declaredType else {
                    throw AnalyzerError("SWIFT_ASSIGNMENT_TYPE_MISMATCH")
                }
                let liftedExpr = try liftExpression(initializer.value, context)
                context.environment[varName] = declaredType
                if isVar {
                    context.mutableVariables.insert(varName)
                }
                result.append(
                    try spanned([
                        ("kind", .string("let")),
                        ("name", .string(varName)),
                        ("type", .string(declaredType)),
                        ("expression", liftedExpr),
                    ], varDecl, context)
                )
            }
            continue
        }

        let rawExpr: ExprSyntax?
        if let exprStmt = item.item.as(ExpressionStmtSyntax.self) {
            rawExpr = exprStmt.expression
        } else if let expr = item.item.as(ExprSyntax.self) {
            rawExpr = expr
        } else {
            rawExpr = nil
        }

        if let expr = rawExpr {
            if let conditional = expr.as(IfExprSyntax.self) {
                result.append(try liftIf(conditional, &context))
                continue
            }
            if let infix = expr.as(InfixOperatorExprSyntax.self) {
                var assignOp: String? = nil
                if infix.operator.is(AssignmentExprSyntax.self) {
                    assignOp = "="
                } else if let binOp = infix.operator.as(BinaryOperatorExprSyntax.self) {
                    let text = binOp.operator.text
                    if text == "=" || text == "+=" || text == "-=" || text == "*=" || text == "/=" || text == "%=" {
                        assignOp = text
                    }
                }
                if let op = assignOp {
                    guard let targetRef = unwrap(infix.leftOperand).as(DeclReferenceExprSyntax.self) else {
                        throw AnalyzerError("SWIFT_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET")
                    }
                    let targetName = targetRef.baseName.text
                    if context.parameterNames.contains(targetName) {
                        throw AnalyzerError("SWIFT_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:\(targetName)")
                    }
                    if context.loopVariables.contains(targetName) {
                        throw AnalyzerError("SWIFT_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:\(targetName)")
                    }
                    guard let targetType = context.environment[targetName] else {
                        throw AnalyzerError("SWIFT_ASSIGNMENT_TARGET_NOT_DECLARED:\(targetName)")
                    }
                    guard context.mutableVariables.contains(targetName) else {
                        throw AnalyzerError("SWIFT_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:\(targetName)")
                    }

                    let rightType = try inferredType(infix.rightOperand, context)
                    guard rightType == targetType else {
                        throw AnalyzerError("SWIFT_ASSIGNMENT_TYPE_MISMATCH")
                    }

                    if op == "=" {
                        let liftedVal = try liftExpression(infix.rightOperand, context)
                        result.append(
                            try spanned([
                                ("kind", .string("assign")),
                                ("name", .string(targetName)),
                                ("expression", liftedVal),
                            ], item.item, context)
                        )
                    } else {
                        let binaryOp = String(op.dropLast())
                        let leftSpanned = try spanned([
                            ("kind", .string("name")),
                            ("value", .string(targetName)),
                        ], infix.leftOperand, context)
                        let rightSpanned = try liftExpression(infix.rightOperand, context)
                        let binaryExpr = try spanned([
                            ("kind", .string("binary")),
                            ("operator", .string(binaryOp)),
                            ("left", leftSpanned),
                            ("right", rightSpanned),
                        ], infix, context)
                        result.append(
                            try spanned([
                                ("kind", .string("assign")),
                                ("name", .string(targetName)),
                                ("expression", binaryExpr),
                            ], item.item, context)
                        )
                    }
                    continue
                }
            }
        }

        if let conditional = item.item.as(IfExprSyntax.self) {
            result.append(try liftIf(conditional, &context))
            continue
        }

        throw AnalyzerError("SWIFT_UNSUPPORTED_STATEMENT:\(item.item.kind)")
    }
    return result
}

func liftIf(_ conditional: IfExprSyntax, _ context: inout LiftContext) throws -> JSONValue {
    // `if let` / `if case` / `if #available` bind, destructure or query the
    // platform; the subset has no canonical form for any of them, so only a
    // single plain boolean expression is accepted.
    guard conditional.conditions.count == 1,
        let element = conditional.conditions.first
    else {
        throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION")
    }
    guard case .expression(let rawCondition) = element.condition else {
        throw AnalyzerError("SWIFT_UNSUPPORTED_CONDITION:\(element.condition.kind)")
    }
    let condition = unwrap(rawCondition)
    let condType = try inferredType(condition, context)
    guard condType == "boolean" else {
        throw AnalyzerError("SWIFT_CONDITION_MUST_BE_BOOLEAN")
    }
    var thenContext = context
    let thenStatements = try liftStatements(conditional.body.statements, &thenContext)

    var elseBody: [JSONValue] = []
    if let elseBlock = conditional.elseBody {
        switch elseBlock {
        case .codeBlock(let block):
            var elseContext = context
            elseBody = try liftStatements(block.statements, &elseContext)
        case .ifExpr(let chained):
            var chainedContext = context
            elseBody = [try liftIf(chained, &chainedContext)]
        }
    }
    return try spanned([
        ("kind", .string("if")),
        ("condition", try liftExpression(condition, context)),
        ("then", .array(thenStatements)),
        ("else", .array(elseBody)),
    ], conditional, context)
}

// MARK: - Functions

func liftFunction(_ declaration: FunctionDeclSyntax, _ context: LiftContext) throws -> JSONValue {
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
    var environment: [String: String] = [:]
    var parameterNames: Set<String> = []
    for parameter in declaration.signature.parameterClause.parameters {
        // `func f(_ value: Int)` -> the binding name is `value`; with a label
        // (`func f(of value: Int)`) it is the second name.
        let name = (parameter.secondName ?? parameter.firstName).text
        guard name != "_" else { throw AnalyzerError("SWIFT_PARAMETER_NAME_REQUIRED") }
        if parameter.defaultValue != nil {
            throw AnalyzerError("SWIFT_DEFAULT_ARGUMENT_OUTSIDE_CERTIFIED_SUBSET")
        }
        let type = try canonicalType(parameter.type)
        environment[name] = type
        parameterNames.insert(name)
        parameters.append(
            try spanned([
                ("name", .string(name)),
                ("type", .string(type)),
            ], parameter, context)
        )
    }

    guard let returnClause = declaration.signature.returnClause else {
        throw AnalyzerError("SWIFT_EXPLICIT_RETURN_TYPE_REQUIRED")
    }

    var functionContext = LiftContext(
        sourceFile: context.sourceFile,
        emittedTarget: context.emittedTarget,
        environment: environment,
        mutableVariables: [],
        parameterNames: parameterNames,
        loopVariables: [],
        inLoop: false)
    return try spanned([
        ("name", .string(declaration.name.text)),
        ("parameters", .array(parameters)),
        ("return_type", .string(try canonicalType(returnClause.type))),
        ("body", .array(try liftStatements(body.statements, &functionContext))),
    ], declaration, context)
}

func moduleSubject(_ statement: CodeBlockItemSyntax, _ context: LiftContext) throws -> JSONValue {
    if let declaration = statement.item.as(FunctionDeclSyntax.self) {
        let modifierNames = Set(declaration.modifiers.map { $0.name.text })
        let visibility: String
        if modifierNames.contains("private") {
            visibility = "private"
        } else if modifierNames.contains("fileprivate") {
            visibility = "fileprivate"
        } else if modifierNames.contains("public") {
            visibility = "public"
        } else if modifierNames.contains("package") {
            visibility = "package"
        } else {
            visibility = "internal"
        }
        let parameters = declaration.signature.parameterClause.parameters.map { parameter in
            JSONValue.object([
                ("name", .string(parameter.secondName?.text ?? parameter.firstName.text)),
                ("source_type", .string(parameter.type.trimmedDescription)),
            ])
        }
        let supportedParameters = declaration.signature.parameterClause.parameters.allSatisfy {
            $0.defaultValue == nil
        }
        let analyzable = declaration.body != nil
            && declaration.signature.effectSpecifiers?.asyncSpecifier == nil
            && declaration.signature.effectSpecifiers?.throwsClause == nil
            && declaration.genericParameterClause == nil
            && declaration.attributes.isEmpty
            && supportedParameters
        return try spanned([
            ("name", .string(declaration.name.text)),
            ("qualified_name", .string(declaration.name.text)),
            ("declaration_kind", .string("FunctionDeclSyntax")),
            ("analyzable", .bool(analyzable)),
            ("signature", .object([
                ("parameters", .array(parameters)),
                ("source_return_type", .string(
                    declaration.signature.returnClause?.type.trimmedDescription ?? "")),
                ("visibility", .string(visibility)),
                ("storage", .string("file-scope")),
            ])),
        ], declaration, context)
    }

    let name: String
    if let imported = statement.item.as(ImportDeclSyntax.self) {
        name = imported.path.trimmedDescription
    } else if let declaration = statement.item.as(ClassDeclSyntax.self) {
        name = declaration.name.text
    } else if let declaration = statement.item.as(StructDeclSyntax.self) {
        name = declaration.name.text
    } else if let declaration = statement.item.as(EnumDeclSyntax.self) {
        name = declaration.name.text
    } else if let declaration = statement.item.as(ProtocolDeclSyntax.self) {
        name = declaration.name.text
    } else {
        name = "<\(String(describing: statement.item.kind))@\(statement.position.utf8Offset)>"
    }
    return try spanned([
        ("name", .string(name)),
        ("qualified_name", .string(name)),
        ("declaration_kind", .string(String(describing: statement.item.kind))),
        ("analyzable", .bool(false)),
        ("signature", .object([
            ("visibility", .string("not-applicable")),
            ("storage", .string("not-applicable")),
        ])),
    ], statement, context)
}

// MARK: - Entry point

let arguments = CommandLine.arguments
guard arguments.count == 3 || (arguments.count == 4 && arguments[3] == "--emitted-target") else {
    FileHandle.standardError.write(
        Data("usage: ElmosSwiftAnalyzer <source> <function> [--emitted-target]\n".utf8)
    )
    exit(2)
}

let sourcePath = URL(fileURLWithPath: arguments[1]).standardizedFileURL
let functionName = arguments[2]
let inventoryMode = functionName == "--inventory"
if inventoryMode && arguments.count != 3 {
    FileHandle.standardError.write(Data("--inventory does not accept --emitted-target\n".utf8))
    exit(2)
}
let context = LiftContext(
    sourceFile: sourcePath.lastPathComponent,
    emittedTarget: arguments.count == 4,
    environment: [:],
    mutableVariables: [],
    parameterNames: [],
    loopVariables: [],
    inLoop: false)

do {
    let source = try String(contentsOf: sourcePath, encoding: .utf8)
    let parsed = Parser.parse(source: source)

    // SwiftSyntax deliberately does NOT apply operator precedence while
    // parsing: `a + b * c` arrives as one flat `SequenceExprSyntax`, and
    // `InfixOperatorExprSyntax` only exists after a separate folding pass.
    // The fold uses the compiler's own standard operator table rather than a
    // hand-rolled precedence ladder, so `a - b - c` and `a + b * c` associate
    // exactly as swiftc associates them. A fold that cannot resolve an
    // operator fails closed instead of leaving an unfolded sequence behind.
    var foldingFailures: [String] = []
    let folded = OperatorTable.standardOperators.foldAll(parsed) { error in
        let text = "\(error)"
            .replacingOccurrences(of: ":", with: "-")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: "_")
        foldingFailures.append("SWIFT_OPERATOR_FOLDING_FAILED:\(text)")
    }
    if let failure = foldingFailures.first {
        FileHandle.standardError.write(Data((failure + "\n").utf8))
        exit(1)
    }
    guard let tree = folded.as(SourceFileSyntax.self) else {
        FileHandle.standardError.write(
            Data("SWIFT_OPERATOR_FOLDING_FAILED:not_a_source_file\n".utf8))
        exit(1)
    }

    // Parser diagnostics are carried, not swallowed: a source that does not
    // parse cleanly blocks emission downstream, exactly as in Analyzer.java.
    let converter = SourceLocationConverter(
        fileName: sourcePath.lastPathComponent, tree: parsed)
    let diagnostics = ParseDiagnosticsGenerator.diagnostics(for: parsed)
        .filter { $0.diagMessage.severity == .error }
        .map { diagnostic -> String in
            let line = converter.location(for: diagnostic.position).line
            // `MessageID.id` is private in SwiftDiagnostics, so the
            // human-readable message is the only public identifier available.
            // It is flattened to a single `CODE:line`-shaped token so the
            // diagnostics list keeps the same shape the JDK and Roslyn
            // analyzers emit.
            let text = diagnostic.diagMessage.message
                .replacingOccurrences(of: ":", with: "-")
                .split(whereSeparator: { $0.isWhitespace })
                .joined(separator: "_")
            return "\(text):\(line)"
        }
        .sorted()

    if inventoryMode {
        let subjects = try tree.statements.map { try moduleSubject($0, context) }
        let output = JSONValue.object([
            ("schema_version", .string("1.0.0")),
            ("kind", .string("elmos.typed-pure-module-inventory")),
            ("profile", .string("typed-pure-module-v1")),
            ("source_language", .string("swift")),
            ("source_file", .string(sourcePath.lastPathComponent)),
            ("analyzer", .string("SwiftSyntax")),
            ("analyzer_version", .string(swiftSyntaxVersion)),
            ("enumeration_status", .string(diagnostics.isEmpty ? "PASSED" : "FAILED")),
            ("subjects", .array(subjects)),
            ("diagnostics", .array(diagnostics.map { JSONValue.string($0) })),
        ])
        print(output.encoded)
        exit(0)
    }

    var functions: [JSONValue] = []
    var failures: [String] = []
    for statement in tree.statements {
        guard let declaration = statement.item.as(FunctionDeclSyntax.self),
            declaration.name.text == functionName
        else { continue }
        do {
            functions.append(try liftFunction(declaration, context))
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
