// Kotlin frontend for the polyglot route engine.
//
// WHY PSI AND NOT A HAND-ROLLED PARSER.  The PHP frontend is built on
// `ext/tokenizer` and the Go frontend on `go/parser` for the same reason this
// one is built on the Kotlin compiler's own PSI: a hand-rolled front end is a
// second, unaudited definition of the language, and every place it disagrees
// with the real compiler is a silent wrong answer rather than a rejection.
// `kotlin-compiler.jar` ships the production parser; this file only walks it.
//
// WHY THE OPT-IN BELOW.  `KotlinCoreEnvironment` is K1 API and the compiler
// marks it deprecated-in-waiting.  Parsing is the one part of K1 that is not
// being reworked -- PSI is shared with the IDE -- so the opt-in is recorded
// here explicitly rather than silenced globally with a compiler flag.  Kotlin
// 2.2.20 has `K1Deprecation` but not the later
// `CompilerConfiguration.Internals` marker; naming that newer marker made the
// analyzer itself uncompilable under the exact 2.2.20 route toolchain.  If a
// future Kotlin removes this API, this file must fail to compile: that is the
// point.
@file:OptIn(
    org.jetbrains.kotlin.K1Deprecation::class,
)
@file:Suppress("DEPRECATION", "K1_DEPRECATION")

import com.intellij.openapi.util.Disposer
import com.intellij.psi.PsiComment
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiErrorElement
import com.intellij.psi.PsiFileFactory
import com.intellij.psi.util.PsiTreeUtil
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.idea.KotlinFileType
import org.jetbrains.kotlin.lexer.KtTokens
import org.jetbrains.kotlin.psi.KtBinaryExpression
import org.jetbrains.kotlin.psi.KtBlockExpression
import org.jetbrains.kotlin.psi.KtCallExpression
import org.jetbrains.kotlin.psi.KtClassOrObject
import org.jetbrains.kotlin.psi.KtConstantExpression
import org.jetbrains.kotlin.psi.KtDotQualifiedExpression
import org.jetbrains.kotlin.psi.KtExpression
import org.jetbrains.kotlin.psi.KtFile
import org.jetbrains.kotlin.psi.KtIfExpression
import org.jetbrains.kotlin.psi.KtNameReferenceExpression
import org.jetbrains.kotlin.psi.KtNamedFunction
import org.jetbrains.kotlin.psi.KtParenthesizedExpression
import org.jetbrains.kotlin.psi.KtProperty
import org.jetbrains.kotlin.psi.KtReturnExpression
import org.jetbrains.kotlin.psi.KtStringTemplateExpression
import org.jetbrains.kotlin.psi.KtTypeAlias
import org.jetbrains.kotlin.psi.KtTypeReference
import java.io.File

private const val ANALYZER_NAME = "kotlin-compiler PSI"
private const val BATCH_PREFIX = "--functions="

/** Carries a rejection out of one function's analysis without killing batch mode. */
private class DomainRejection(val code: String) : RuntimeException(code, null, false, false)

private var batchMode = false

private fun fail(code: String): Nothing {
    if (batchMode) throw DomainRejection(code)
    System.err.println(code)
    kotlin.system.exitProcess(2)
}

// ---------------------------------------------------------------- JSON output
//
// Hand-written rather than pulled from a library: the analyzer runs from a jar
// built on demand with only kotlin-compiler.jar on the classpath, and adding a
// JSON dependency would mean adding a second pinned artifact to the toolchain
// closure for something this small.

private fun jsonString(value: String): String {
    val out = StringBuilder("\"")
    for (character in value) {
        when (character) {
            '"' -> out.append("\\\"")
            '\\' -> out.append("\\\\")
            '\n' -> out.append("\\n")
            '\r' -> out.append("\\r")
            '\t' -> out.append("\\t")
            '' -> out.append("\\b")
            '' -> out.append("\\f")
            else ->
                if (character < ' ' || character == '') {
                    out.append(String.format("\\u%04x", character.code))
                } else {
                    out.append(character)
                }
        }
    }
    return out.append('"').toString()
}

private fun jsonNumber(value: Double): String {
    if (value.isNaN() || value.isInfinite()) fail("KOTLIN_NON_FINITE_LITERAL")
    if (value == Math.floor(value) && Math.abs(value) < 1e15) {
        // 3.0 must not print as "3": the IR distinguishes number from integer
        // by the JSON token, and a bare 3 would relift as an integer literal.
        return "${value.toLong()}.0"
    }
    return value.toString()
}

private fun json(value: Any?): String = when (value) {
    null -> "null"
    is String -> jsonString(value)
    is Boolean -> value.toString()
    is Long -> value.toString()
    is Int -> value.toString()
    is Double -> jsonNumber(value)
    is List<*> -> value.joinToString(",", "[", "]") { json(it) }
    is Map<*, *> ->
        value.entries.joinToString(",", "{", "}") { jsonString(it.key as String) + ":" + json(it.value) }
    else -> fail("KOTLIN_JSON_ENCODE_FAILED")
}

// ------------------------------------------------------------------ PSI setup

private fun parse(sourcePath: String, text: String): KtFile {
    val disposable = Disposer.newDisposable()
    val environment =
        KotlinCoreEnvironment.createForProduction(
            disposable,
            CompilerConfiguration(),
            EnvironmentConfigFiles.JVM_CONFIG_FILES,
        )
    val factory = PsiFileFactory.getInstance(environment.project)
    val name = File(sourcePath).name
    val file = factory.createFileFromText(name, KotlinFileType.INSTANCE, text)
    if (file !is KtFile) fail("KOTLIN_PARSE_FAILED:not-a-kotlin-file")
    return file
}

/**
 * PSI never throws on malformed input: it inserts [PsiErrorElement] and keeps
 * going. Treating that as a successful parse is how a frontend starts lifting
 * half a function, so the check is explicit and happens before anything else.
 */
private fun firstSyntaxError(file: KtFile): String? {
    val error = PsiTreeUtil.findChildOfType(file, PsiErrorElement::class.java) ?: return null
    return error.errorDescription
}

// ------------------------------------------------------------------ type map
//
// Long/Double/Boolean/String only.  Kotlin's `Int` is deliberately absent: the
// certified integer domain is 64-bit two's complement across every route, and
// accepting `Int` here would let a 32-bit-overflow source lift into an IR that
// every other target executes at 64 bits -- a wrong answer, not a rejection.

private fun canonicalType(reference: KtTypeReference?): String {
    val text = reference?.text?.trim() ?: fail("KOTLIN_EXPLICIT_TYPE_REQUIRED")
    return when (text) {
        "Long", "kotlin.Long" -> "integer"
        "Double", "kotlin.Double" -> "number"
        "Boolean", "kotlin.Boolean" -> "boolean"
        "String", "kotlin.String" -> "string"
        else -> fail("KOTLIN_UNSUPPORTED_TYPE:$text")
    }
}

// -------------------------------------------------------------- emitted target

private val EMITTED_BINARY_HELPERS = mapOf(
    "elmosCheckedAdd" to "+",
    "elmosCheckedSub" to "-",
    "elmosCheckedMul" to "*",
    "elmosCheckedDiv" to "/",
    "elmosCheckedMod" to "%",
)
private const val EMITTED_NON_ZERO_HELPER = "elmosNonZero"

private val EMITTED_MATH_HELPERS = mapOf(
    "addExact" to "+",
    "subtractExact" to "-",
    "multiplyExact" to "*",
)

private val SUPPORTED_OPERATORS =
    setOf("+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||")

// ------------------------------------------------------------------ lifting

private fun expression(node: KtExpression?, emittedTarget: Boolean): Map<String, Any?> {
    if (node == null) fail("KOTLIN_UNSUPPORTED_EXPRESSION:null")
    return when (node) {
        is KtParenthesizedExpression -> expression(node.expression, emittedTarget)
        is KtNameReferenceExpression -> mapOf("kind" to "name", "value" to node.getReferencedName())
        is KtConstantExpression -> constant(node)
        is KtStringTemplateExpression -> stringLiteral(node)
        is KtBinaryExpression -> binary(node, emittedTarget)
        is KtCallExpression -> emittedHelper(node, emittedTarget)
        is KtDotQualifiedExpression -> emittedDotQualified(node, emittedTarget)
        else -> fail("KOTLIN_UNSUPPORTED_EXPRESSION:${node::class.java.simpleName}")
    }
}

private fun constant(node: KtConstantExpression): Map<String, Any?> {
    val text = node.text
    if (text == "true" || text == "false") {
        return mapOf("kind" to "literal", "value" to (text == "true"))
    }
    // Underscore separators and the `L`/`F` suffixes are spelling, not value.
    val normalized = text.replace("_", "")
    val looksReal =
        normalized.contains('.') ||
            normalized.contains('e') ||
            normalized.contains('E') ||
            normalized.endsWith("f") ||
            normalized.endsWith("F")
    if (looksReal) {
        val real = normalized.removeSuffix("f").removeSuffix("F")
        val parsed = real.toDoubleOrNull() ?: fail("KOTLIN_INVALID_LITERAL:$text")
        return mapOf("kind" to "literal", "value" to parsed)
    }
    val integer = normalized.removeSuffix("L").removeSuffix("l")
    val parsed = integer.toLongOrNull() ?: fail("KOTLIN_INVALID_LITERAL:$text")
    return mapOf("kind" to "literal", "value" to parsed)
}

private fun stringLiteral(node: KtStringTemplateExpression): Map<String, Any?> {
    // Only a constant string is a literal.  `"$name"` is an interpolation --
    // a computation with a toString-dependent result -- and must be rejected
    // rather than lifted as whatever it happens to render to.
    if (node.hasInterpolation()) fail("KOTLIN_STRING_INTERPOLATION_UNSUPPORTED")
    val builder = StringBuilder()
    for (entry in node.entries) {
        builder.append(unescape(entry.text))
    }
    return mapOf("kind" to "literal", "value" to builder.toString())
}

private fun unescape(raw: String): String {
    if (!raw.startsWith("\\")) return raw
    return when (raw) {
        "\\n" -> "\n"
        "\\r" -> "\r"
        "\\t" -> "\t"
        "\\b" -> ""
        "\\\\" -> "\\"
        "\\\"" -> "\""
        "\\'" -> "'"
        "\\$" -> "$"
        else ->
            if (raw.startsWith("\\u") && raw.length == 6) {
                raw.substring(2).toIntOrNull(16)?.toChar()?.toString()
                    ?: fail("KOTLIN_INVALID_ESCAPE:$raw")
            } else {
                fail("KOTLIN_INVALID_ESCAPE:$raw")
            }
    }
}

private fun binary(node: KtBinaryExpression, emittedTarget: Boolean): Map<String, Any?> {
    val operator = node.operationReference.text
    if (operator !in SUPPORTED_OPERATORS) fail("KOTLIN_UNSUPPORTED_OPERATOR:$operator")
    return mapOf(
        "kind" to "binary",
        "operator" to operator,
        "left" to expression(node.left, emittedTarget),
        "right" to expression(node.right, emittedTarget),
    )
}

private fun emittedHelper(node: KtCallExpression, emittedTarget: Boolean): Map<String, Any?> {
    if (!emittedTarget) fail("KOTLIN_UNSUPPORTED_EXPRESSION:KtCallExpression")
    val callee = node.calleeExpression
    if (callee !is KtNameReferenceExpression) fail("KOTLIN_EMITTED_HELPER_CALLEE_INVALID")
    val name = callee.getReferencedName()
    val arguments = node.valueArguments
    if (node.lambdaArguments.isNotEmpty()) fail("KOTLIN_EMITTED_HELPER_ARITY:$name")
    val operator = EMITTED_BINARY_HELPERS[name]
    if (operator != null) {
        if (arguments.size != 2) fail("KOTLIN_EMITTED_HELPER_ARITY:$name")
        return mapOf(
            "kind" to "binary",
            "operator" to operator,
            "left" to expression(arguments[0].getArgumentExpression(), true),
            "right" to expression(arguments[1].getArgumentExpression(), true),
        )
    }
    if (name == EMITTED_NON_ZERO_HELPER) {
        if (arguments.size != 1) fail("KOTLIN_EMITTED_HELPER_ARITY:$name")
        return expression(arguments[0].getArgumentExpression(), true)
    }
    fail("KOTLIN_EMITTED_HELPER_UNRECOGNIZED:$name")
}

private fun emittedDotQualified(
    node: KtDotQualifiedExpression,
    emittedTarget: Boolean,
): Map<String, Any?> {
    if (!emittedTarget) fail("KOTLIN_UNSUPPORTED_EXPRESSION:KtDotQualifiedExpression")
    val receiver = node.receiverExpression
    val selector = node.selectorExpression

    // Kotlin/JVM's checked Long operations are emitted through java.lang.Math.
    // Re-lifting the call to the canonical binary node records the operation,
    // while the emitted helper-source verifier separately proves that the
    // compensation was not removed.
    if (receiver.text == "Math" && selector is KtCallExpression) {
        val callee = selector.calleeExpression as? KtNameReferenceExpression
            ?: fail("KOTLIN_EMITTED_MATH_CALLEE_INVALID")
        val name = callee.getReferencedName()
        val operator = EMITTED_MATH_HELPERS[name]
            ?: fail("KOTLIN_EMITTED_MATH_HELPER_UNRECOGNIZED:$name")
        if (selector.lambdaArguments.isNotEmpty() || selector.valueArguments.size != 2) {
            fail("KOTLIN_EMITTED_HELPER_ARITY:Math.$name")
        }
        return mapOf(
            "kind" to "binary",
            "operator" to operator,
            "left" to expression(selector.valueArguments[0].getArgumentExpression(), true),
            "right" to expression(selector.valueArguments[1].getArgumentExpression(), true),
        )
    }

    // The emitter spells the one permitted numeric widening explicitly.
    // Canonical IR records the original integer expression under a `number`
    // return or binding; the target syntax's `.toDouble()` is compensation,
    // not an extra semantic node.
    if (selector is KtCallExpression) {
        val callee = selector.calleeExpression as? KtNameReferenceExpression
        if (
            callee?.getReferencedName() == "toDouble" &&
            selector.valueArguments.isEmpty() &&
            selector.lambdaArguments.isEmpty()
        ) {
            return expression(receiver, true)
        }
    }

    // Kotlin cannot spell -2^63 as a signed literal; the emitter uses the
    // standard constant because `-9223372036854775808L` does not compile.
    if (
        receiver.text == "Long" &&
        selector is KtNameReferenceExpression &&
        selector.getReferencedName() == "MIN_VALUE"
    ) {
        return mapOf("kind" to "literal", "value" to Long.MIN_VALUE)
    }
    fail("KOTLIN_EMITTED_DOT_QUALIFIED_UNRECOGNIZED:${node.text}")
}

private fun ifStatement(node: KtIfExpression, emittedTarget: Boolean): Map<String, Any?> {
    val condition = node.condition ?: fail("KOTLIN_IF_CONDITION_REQUIRED")
    val thenBranch = node.then ?: fail("KOTLIN_IF_THEN_REQUIRED")
    val elseBranch = node.`else`
    val elseBody: List<Map<String, Any?>> = when (elseBranch) {
        null -> emptyList()
        // `else if` is an else branch whose expression is itself an if -- it is
        // spelling, not a construct -- so it lifts into the nested shape every
        // other frontend in this engine already produces.
        is KtIfExpression -> listOf(ifStatement(elseBranch, emittedTarget))
        is KtBlockExpression -> statements(elseBranch, emittedTarget)
        else -> fail("KOTLIN_UNSUPPORTED_STATEMENT:${elseBranch::class.java.simpleName}")
    }
    val thenBody: List<Map<String, Any?>> =
        if (thenBranch is KtBlockExpression) {
            statements(thenBranch, emittedTarget)
        } else {
            fail("KOTLIN_IF_BLOCK_BODY_REQUIRED")
        }
    return mapOf(
        "kind" to "if",
        "condition" to expression(condition, emittedTarget),
        "then" to thenBody,
        "else" to elseBody,
    )
}

private fun statements(block: KtBlockExpression, emittedTarget: Boolean): List<Map<String, Any?>> {
    val result = ArrayList<Map<String, Any?>>()
    for (statement in block.statements) {
        when (statement) {
            is KtReturnExpression -> {
                if (statement.getTargetLabel() != null) fail("KOTLIN_LABELED_RETURN_UNSUPPORTED")
                val value = statement.returnedExpression ?: fail("KOTLIN_RETURN_EXPRESSION_REQUIRED")
                result.add(mapOf("kind" to "return", "expression" to expression(value, emittedTarget)))
            }
            is KtIfExpression -> result.add(ifStatement(statement, emittedTarget))
            is KtProperty -> {
                if (statement.isVar) fail("KOTLIN_MUTABLE_LOCAL_OUTSIDE_CERTIFIED_SUBSET")
                if (statement.delegateExpression != null) {
                    fail("KOTLIN_DELEGATED_LOCAL_OUTSIDE_CERTIFIED_SUBSET")
                }
                val name = statement.name ?: fail("KOTLIN_LOCAL_NAME_REQUIRED")
                val initializer = statement.initializer ?: fail("KOTLIN_LOCAL_INITIALIZER_REQUIRED")
                result.add(
                    mapOf(
                        "kind" to "let",
                        "name" to name,
                        "type" to canonicalType(statement.typeReference),
                        "expression" to expression(initializer, emittedTarget),
                    )
                )
            }
            else -> fail("KOTLIN_UNSUPPORTED_STATEMENT:${statement::class.java.simpleName}")
        }
    }
    return result
}

// ---------------------------------------------------------------- source spans

private class ByteOffsets(text: String) {
    // PSI offsets are UTF-16 char offsets; every span in this engine is a byte
    // offset into the file as stored.  Converting per element keeps a non-ASCII
    // identifier from silently shifting every span after it.
    private val prefixBytes = IntArray(text.length + 1)

    init {
        var total = 0
        for (index in text.indices) {
            prefixBytes[index] = total
            total += utf8Length(text, index)
        }
        prefixBytes[text.length] = total
    }

    private fun utf8Length(text: String, index: Int): Int {
        val code = text[index].code
        return when {
            code < 0x80 -> 1
            code < 0x800 -> 2
            // A surrogate pair is 4 bytes total; charge them 2 each so any
            // boundary between them still lands on a real byte offset.
            Character.isSurrogate(text[index]) -> 2
            else -> 3
        }
    }

    fun byteOffset(charOffset: Int): Int =
        prefixBytes[charOffset.coerceIn(0, prefixBytes.size - 1)]
}

private fun sourceSpan(
    fileName: String,
    offsets: ByteOffsets,
    element: PsiElement,
): Map<String, Any?> =
    mapOf(
        "file" to fileName,
        "start_byte" to offsets.byteOffset(element.textRange.startOffset),
        "end_byte" to offsets.byteOffset(element.textRange.endOffset),
    )

// ------------------------------------------------------------------ inventory

private fun functionSubject(
    fileName: String,
    offsets: ByteOffsets,
    qualifiedName: String,
    declaration: KtNamedFunction,
): Map<String, Any?> {
    val parameters = declaration.valueParameters.map {
        mapOf(
            "name" to (it.name ?: ""),
            "source_type" to (it.typeReference?.text ?: ""),
        )
    }
    val receiver = declaration.receiverTypeReference?.text ?: ""
    val analyzable =
        receiver.isEmpty() &&
            declaration.typeParameters.isEmpty() &&
            declaration.bodyBlockExpression != null &&
            !declaration.hasModifier(KtTokens.SUSPEND_KEYWORD) &&
            !declaration.hasModifier(KtTokens.INLINE_KEYWORD)
    return mapOf(
        "name" to (declaration.name ?: "<anonymous>"),
        "qualified_name" to qualifiedName,
        "declaration_kind" to if (receiver.isEmpty()) "function" else "extension-function",
        "analyzable" to analyzable,
        "source_span" to sourceSpan(fileName, offsets, declaration),
        "signature" to mapOf(
            "parameters" to parameters,
            "source_return_type" to (declaration.typeReference?.text ?: ""),
            "receiver" to receiver,
            "visibility" to
                if (declaration.hasModifier(KtTokens.PRIVATE_KEYWORD)) "private" else "external",
            "storage" to "file-scope",
        ),
    )
}

private fun moduleInventory(
    fileName: String,
    file: KtFile,
    offsets: ByteOffsets,
    diagnostics: List<String>,
): Map<String, Any?> {
    val packageName = file.packageFqName.asString()
    fun qualify(name: String): String = if (packageName.isEmpty()) name else "$packageName.$name"
    val subjects = ArrayList<Map<String, Any?>>()

    for (directive in file.importDirectives) {
        val name = directive.importedFqName?.asString() ?: directive.text
        subjects.add(
            mapOf(
                "name" to name,
                "qualified_name" to name,
                "declaration_kind" to "import",
                "analyzable" to false,
                "source_span" to sourceSpan(fileName, offsets, directive),
                "signature" to emptyMap<String, Any?>(),
            )
        )
    }
    for (comment in PsiTreeUtil.findChildrenOfType(file, PsiComment::class.java)) {
        val text = comment.text.trim()
        // Only compiler-directive-looking comments are inventory subjects; a
        // prose comment is not a declaration and must not inflate the count.
        if (!text.startsWith("//@") && !text.startsWith("/*@")) continue
        subjects.add(
            mapOf(
                "name" to "<comment-directive>",
                "qualified_name" to qualify("<comment-directive>"),
                "declaration_kind" to "kotlin-comment-directive",
                "analyzable" to false,
                "source_span" to sourceSpan(fileName, offsets, comment),
                "signature" to mapOf("directive" to text),
            )
        )
    }
    for (declaration in file.declarations) {
        val name = declaration.name ?: "<anonymous>"
        when (declaration) {
            is KtNamedFunction ->
                subjects.add(functionSubject(fileName, offsets, qualify(name), declaration))
            is KtClassOrObject ->
                subjects.add(
                    mapOf(
                        "name" to name,
                        "qualified_name" to qualify(name),
                        "declaration_kind" to "type",
                        "analyzable" to false,
                        "source_span" to sourceSpan(fileName, offsets, declaration),
                        "signature" to mapOf("source_type" to (declaration.getSuperTypeList()?.text ?: "")),
                    )
                )
            is KtProperty ->
                subjects.add(
                    mapOf(
                        "name" to name,
                        "qualified_name" to qualify(name),
                        "declaration_kind" to if (declaration.isVar) "variable" else "constant",
                        "analyzable" to false,
                        "source_span" to sourceSpan(fileName, offsets, declaration),
                        "signature" to mapOf("source_type" to (declaration.typeReference?.text ?: "")),
                    )
                )
            is KtTypeAlias ->
                subjects.add(
                    mapOf(
                        "name" to name,
                        "qualified_name" to qualify(name),
                        "declaration_kind" to "type",
                        "analyzable" to false,
                        "source_span" to sourceSpan(fileName, offsets, declaration),
                        "signature" to mapOf("source_type" to (declaration.getTypeReference()?.text ?: "")),
                    )
                )
            else -> Unit
        }
    }
    return mapOf(
        "schema_version" to "1.0.0",
        "kind" to "elmos.typed-pure-module-inventory",
        "profile" to "typed-pure-module-v1",
        "source_language" to "kotlin",
        "source_file" to fileName,
        "analyzer" to ANALYZER_NAME,
        "analyzer_version" to analyzerVersion(),
        "enumeration_status" to if (diagnostics.isEmpty()) "PASSED" else "FAILED",
        "subjects" to subjects,
        "diagnostics" to diagnostics,
    )
}

// ------------------------------------------------------------------- analysis

private fun analyzerVersion(): String = KotlinCompilerVersion.getVersion() ?: "unknown"

private fun analyzeFunction(
    fileName: String,
    file: KtFile,
    functionName: String,
    emittedTarget: Boolean,
): Map<String, Any?> {
    val matches = file.declarations
        .filterIsInstance<KtNamedFunction>()
        .filter { it.name == functionName && it.receiverTypeReference == null }
    // Selection is by exact top-level function name.  Kotlin permits overloads,
    // but this bounded analyzer has no signature selector, so choosing the first
    // declaration would make source order decide semantics.  Zero and multiple
    // matches are separate explicit failures; exactly one is the only safe case.
    if (matches.isEmpty()) fail("FUNCTION_NOT_FOUND:$functionName")
    if (matches.size != 1) fail("KOTLIN_FUNCTION_NAME_AMBIGUOUS")
    val candidate = matches.single()
    if (candidate.typeParameters.isNotEmpty()) fail("KOTLIN_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    if (candidate.hasModifier(KtTokens.SUSPEND_KEYWORD)) fail("KOTLIN_SUSPEND_FUNCTION_UNSUPPORTED")
    // An expression body (`fun f() = expr`) can omit the return type and lean
    // on inference.  Requiring a block body keeps this frontend from ever
    // depending on type inference it does not run.
    val body = candidate.bodyBlockExpression ?: fail("KOTLIN_BLOCK_BODY_REQUIRED")
    val parameters = candidate.valueParameters.map { parameter ->
        val name = parameter.name ?: fail("KOTLIN_PARAMETER_NAME_REQUIRED")
        if (parameter.hasDefaultValue()) fail("KOTLIN_DEFAULT_ARGUMENT_UNSUPPORTED")
        if (parameter.isVarArg) fail("KOTLIN_VARARG_UNSUPPORTED")
        mapOf("name" to name, "type" to canonicalType(parameter.typeReference))
    }
    return mapOf(
        "schema_version" to "1.0.0",
        "source_language" to "kotlin",
        "source_file" to fileName,
        "analyzer" to ANALYZER_NAME,
        "analyzer_version" to analyzerVersion(),
        "functions" to listOf(
            mapOf(
                "name" to (candidate.name ?: ""),
                "parameters" to parameters,
                "return_type" to canonicalType(candidate.typeReference),
                "body" to statements(body, emittedTarget),
            )
        ),
        "diagnostics" to emptyList<String>(),
    )
}

private fun analyzeFunctionGuarded(
    fileName: String,
    file: KtFile,
    functionName: String,
    emittedTarget: Boolean,
): Pair<Map<String, Any?>?, String> =
    try {
        Pair(analyzeFunction(fileName, file, functionName, emittedTarget), "")
    } catch (rejection: DomainRejection) {
        Pair(null, rejection.code)
    }

private fun emitBatch(fileName: String, file: KtFile, names: List<String>, emittedTarget: Boolean) {
    val results = names.map { name ->
        val (payload, code) = analyzeFunctionGuarded(fileName, file, name, emittedTarget)
        if (code.isEmpty()) {
            mapOf("function" to name, "status" to "ok", "error" to null, "value" to payload)
        } else {
            mapOf("function" to name, "status" to "domain_error", "error" to code, "value" to null)
        }
    }
    println(
        json(
            mapOf(
                "schema_version" to "1.0.0",
                "kind" to "elmos.typed-pure-function-batch",
                "source_language" to "kotlin",
                "source_file" to fileName,
                "analyzer" to ANALYZER_NAME,
                "analyzer_version" to analyzerVersion(),
                "results" to results,
            )
        )
    )
}

fun main(rawArguments: Array<String>) {
    var arguments = rawArguments.toList()
    if (arguments.isNotEmpty() && arguments[0] == "--") arguments = arguments.drop(1)
    if (arguments.size < 2 || arguments.size > 3 ||
        (arguments.size == 3 && arguments[2] != "--emitted-target")
    ) {
        fail("USAGE:analyzer SOURCE FUNCTION [--emitted-target]")
    }
    val sourcePath = arguments[0]
    val functionName = arguments[1]
    val emittedTarget = arguments.size == 3
    var batchNames = emptyList<String>()
    if (functionName.startsWith(BATCH_PREFIX)) {
        batchNames = functionName.removePrefix(BATCH_PREFIX)
            .split(",")
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
        if (batchNames.isEmpty()) {
            fail("USAGE:analyzer SOURCE --functions=NAME[,NAME...] [--emitted-target]")
        }
        batchMode = true
    }

    val sourceFile = File(sourcePath)
    val fileName = sourceFile.name
    val text = try {
        sourceFile.readText()
    } catch (error: Exception) {
        fail("KOTLIN_SOURCE_UNREADABLE:${error.javaClass.simpleName}")
    }
    val file = parse(sourcePath, text)
    val offsets = ByteOffsets(text)
    val syntaxError = firstSyntaxError(file)

    if (functionName == "--inventory") {
        val payload =
            if (syntaxError == null) {
                moduleInventory(fileName, file, offsets, emptyList())
            } else {
                mapOf(
                    "schema_version" to "1.0.0",
                    "kind" to "elmos.typed-pure-module-inventory",
                    "profile" to "typed-pure-module-v1",
                    "source_language" to "kotlin",
                    "source_file" to fileName,
                    "analyzer" to ANALYZER_NAME,
                    "analyzer_version" to analyzerVersion(),
                    "enumeration_status" to "FAILED",
                    "subjects" to emptyList<Map<String, Any?>>(),
                    "diagnostics" to listOf("KOTLIN_PARSE_FAILED:$syntaxError"),
                )
            }
        println(json(payload))
        return
    }
    if (syntaxError != null) fail("KOTLIN_PARSE_FAILED:$syntaxError")
    if (batchMode) {
        emitBatch(fileName, file, batchNames, emittedTarget)
        return
    }
    println(json(analyzeFunction(fileName, file, functionName, emittedTarget)))
}
