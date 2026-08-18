<?php

/**
 * ELMOS polyglot route engine -- PHP source frontend.
 *
 * Lifts one function from a PHP source file into the engine's semantic IR for
 * the `typed-pure-function-v1` profile. Everything outside that profile fails
 * closed with a PHP_-prefixed domain error; nothing is inferred, widened or
 * guessed.
 *
 * WHY A TOKENIZER AND NOT A PARSER LIBRARY
 *
 * The other frontends in this engine are the language's own: the JDK Compiler
 * Tree API, CPython's ast, Roslyn, clang's AST dump, SwiftSyntax, go/parser,
 * syn. PHP ships no comparable first-party tree in core -- `ext/ast` (php-ast)
 * exposes the real Zend AST but is a PECL extension, and nikic/PHP-Parser is a
 * faithful but *independent* reimplementation of the parser in userland.
 *
 * `token_get_all()` is the one first-party option: `ext/tokenizer` is a thin
 * wrapper over the Zend scanner itself, so the token stream is the compiler's
 * own lexical analysis, not a re-lex. Called with TOKEN_PARSE it additionally
 * runs the real parser for validation and resolves the context-sensitive
 * tokens. The certified subset is small enough -- typed parameters, `if`,
 * `return`, literals, names, binary operators -- that a precedence-climbing
 * parse over that stream is exact rather than approximate, and every construct
 * it does not know is a refusal rather than a fallback.
 *
 * Three independent layers therefore have to agree before an IR is produced:
 *
 *   1. `php -l` (run by the caller) -- the real compiler accepts the file.
 *   2. This lift over the real token stream, which additionally asserts that
 *      concatenating every token reproduces the source byte-for-byte, so the
 *      byte spans it reports cannot drift from the file the caller hashed.
 *   3. php-ast, when the extension happens to be loaded: the lifted shape is
 *      compared against Zend's own AST for the same function and any
 *      disagreement is fatal. This never *enables* a route -- it can only
 *      refuse one -- so an analysis is not weaker on a host without the
 *      extension, but it is better witnessed on a host with it.
 *
 * Usage: php analyzer.php <source-path> <function-name> [--emitted-target]
 */

declare(strict_types=1);

const SCHEMA_VERSION = '1.0.0';
const ANALYZER_NAME = 'php/ext-tokenizer Zend token stream';
const MAX_SOURCE_BYTES = 2000000;

/**
 * Pinned Zend AST version for the optional cross-check. The node shapes
 * `crossCheckWithZendAst` reads are version-dependent, so this is pinned rather
 * than "whatever the extension supports newest".
 */
const PHP_AST_VERSION = 110;

/**
 * `ast\flags\TYPE_*` restated as plain constants so this file parses and runs
 * on a host without the extension -- referencing `ast\flags\TYPE_LONG`
 * directly would be an undefined-constant Error there. The values are Zend's
 * own IS_* type codes and are stable across AST versions.
 */
const ZEND_TYPE_LONG = 4;
const ZEND_TYPE_DOUBLE = 5;
const ZEND_TYPE_STRING = 6;
const ZEND_TYPE_BOOL = 18;

const CANONICAL_TYPES = [
    'int' => 'integer',
    'float' => 'number',
    'bool' => 'boolean',
    'string' => 'string',
];

/** Binary operators the profile admits, mapped to their canonical spelling. */
const BINARY_OPERATORS = [
    '+' => '+', '-' => '-', '*' => '*', '%' => '%',
    '<' => '<', '>' => '>',
    '<=' => '<=', '>=' => '>=',
    '===' => '==', '!==' => '!=',
    '&&' => '&&', '||' => '||',
];

/**
 * Precedence, high binds tighter. Deliberately *not* PHP's full table: only the
 * operators above appear, and every one of them is left-associative in PHP.
 */
const PRECEDENCE = [
    '*' => 7, '/' => 7, '%' => 7,
    '+' => 6, '-' => 6,
    '.' => 5,
    '<' => 4, '<=' => 4, '>' => 4, '>=' => 4,
    '===' => 3, '!==' => 3,
    '&&' => 2,
    '||' => 1,
];

/**
 * Emitted-target relift: the calls `emitter._PHP_HELPERS` generates, folded back
 * into the canonical binary node they compensate. Mirrors
 * `python_analyzer._EMITTED_BINARY_HELPERS` and `clang_analyzer._EMITTED_HELPERS`.
 */
const EMITTED_BINARY_HELPERS = [
    'elmos_checked_add' => '+',
    'elmos_checked_sub' => '-',
    'elmos_checked_mul' => '*',
    'elmos_checked_div' => '/',
    'elmos_checked_mod' => '%',
    'fmod' => '%',
];
/** Calls that are pure guards: they return their argument or raise. */
const EMITTED_IDENTITY_HELPERS = ['elmos_non_zero_float'];
/** Function names the emitter generates, which are never a lift subject. */
const EMITTED_HELPER_NAMES = [
    'elmos_checked_add', 'elmos_checked_sub', 'elmos_checked_mul',
    'elmos_checked_div', 'elmos_checked_mod', 'elmos_non_zero_float',
];

final class DomainError extends RuntimeException
{
}

function fail(string $code, string $detail = ''): never
{
    throw new DomainError($detail === '' ? $code : $code . ':' . $detail);
}

/** One token: kind is a T_* id or a single-character string. */
final class Tok
{
    public function __construct(
        public readonly int|string $kind,
        public readonly string $text,
        public readonly int $start,
        public readonly int $end,
    ) {
    }
}

/**
 * Tokenize and assert the stream is a lossless partition of the source.
 *
 * The byte spans this analyzer reports are derived from cumulative token
 * lengths, so "the concatenation is the file" is not a sanity check, it is the
 * precondition that makes those spans meaningful.
 */
function lex(string $source): array
{
    $raw = @token_get_all($source, TOKEN_PARSE);
    if (!is_array($raw) || $raw === []) {
        fail('PHP_SOURCE_UNPARSEABLE');
    }
    $tokens = [];
    $offset = 0;
    $rebuilt = '';
    foreach ($raw as $item) {
        if (is_array($item)) {
            $kind = $item[0];
            $text = $item[1];
        } else {
            $kind = $item;
            $text = $item;
        }
        $length = strlen($text);
        $tokens[] = new Tok($kind, $text, $offset, $offset + $length);
        $offset += $length;
        $rebuilt .= $text;
    }
    if ($rebuilt !== $source) {
        fail('PHP_TOKEN_STREAM_NOT_BYTE_EXACT');
    }
    return $tokens;
}

/** Drop whitespace; refuse comments so a span can never cover elided bytes. */
function significant(array $tokens): array
{
    $out = [];
    foreach ($tokens as $token) {
        if ($token->kind === T_WHITESPACE) {
            continue;
        }
        if ($token->kind === T_COMMENT || $token->kind === T_DOC_COMMENT) {
            continue;
        }
        $out[] = $token;
    }
    return $out;
}

final class Cursor
{
    private int $index = 0;

    /** @param list<Tok> $tokens */
    public function __construct(private readonly array $tokens, private readonly string $file)
    {
    }

    public function peek(int $ahead = 0): ?Tok
    {
        return $this->tokens[$this->index + $ahead] ?? null;
    }

    public function next(): Tok
    {
        $token = $this->tokens[$this->index] ?? null;
        if ($token === null) {
            fail('PHP_UNEXPECTED_END_OF_INPUT');
        }
        $this->index++;
        return $token;
    }

    public function atEnd(): bool
    {
        return $this->index >= count($this->tokens);
    }

    public function expect(int|string $kind, string $code): Tok
    {
        $token = $this->peek();
        if ($token === null || $token->kind !== $kind) {
            $seen = $token === null ? 'EOF' : (is_int($token->kind) ? token_name($token->kind) : $token->kind);
            fail($code, $seen);
        }
        return $this->next();
    }

    public function accept(int|string $kind): ?Tok
    {
        $token = $this->peek();
        if ($token !== null && $token->kind === $kind) {
            return $this->next();
        }
        return null;
    }

    public function file(): string
    {
        return $this->file;
    }
}

function span(string $file, int $start, int $end): array
{
    return ['file' => $file, 'start_byte' => $start, 'end_byte' => $end];
}

/** `declare(strict_types=1);` is mandatory: without it the emitted and lifted
 *  parameter types are coercive, and a `string` argument would satisfy an `int`
 *  parameter. The profile's whole type story rests on it. */
function requireStrictTypes(Cursor $cursor): void
{
    $cursor->expect(T_OPEN_TAG, 'PHP_OPEN_TAG_REQUIRED');
    $cursor->expect(T_DECLARE, 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    $cursor->expect('(', 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    $name = $cursor->expect(T_STRING, 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    if (strtolower($name->text) !== 'strict_types') {
        fail('PHP_STRICT_TYPES_DECLARATION_REQUIRED', $name->text);
    }
    $cursor->expect('=', 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    $value = $cursor->expect(T_LNUMBER, 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    if ($value->text !== '1') {
        fail('PHP_STRICT_TYPES_DECLARATION_REQUIRED', $value->text);
    }
    $cursor->expect(')', 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
    $cursor->expect(';', 'PHP_STRICT_TYPES_DECLARATION_REQUIRED');
}

/**
 * Consume one optional file-level `namespace X\Y;` declaration.
 *
 * Accepted rather than refused for two reasons. Real PHP is namespaced, so a
 * frontend that refuses namespaces cannot read the repositories this engine
 * exists to migrate. And `assembly._place_php` puts every assembled unit in its
 * own namespace -- that is what stops two units' helpers from colliding -- so
 * refusing here would make the engine unable to re-analyze its own output.
 *
 * The braced form `namespace X { ... }` is refused: it permits several
 * namespaces per file, and then "the function called X in this file" stops
 * being a single answer.
 */
function acceptNamespace(Cursor $cursor): ?string
{
    if ($cursor->peek() === null || $cursor->peek()->kind !== T_NAMESPACE) {
        return null;
    }
    $cursor->next();
    $name = $cursor->peek();
    if ($name === null || ($name->kind !== T_STRING && $name->kind !== T_NAME_QUALIFIED)) {
        fail('PHP_UNSUPPORTED_STATEMENT', 'anonymous-namespace');
    }
    $cursor->next();
    $terminator = $cursor->peek();
    if ($terminator !== null && $terminator->kind === '{') {
        fail('PHP_BRACED_NAMESPACE_OUTSIDE_CERTIFIED_SUBSET');
    }
    $cursor->expect(';', 'PHP_UNSUPPORTED_STATEMENT');
    return $name->text;
}


function canonicalType(Cursor $cursor, string $code): string
{
    $token = $cursor->peek();
    if ($token === null) {
        fail($code, 'EOF');
    }
    if ($token->kind === '?') {
        fail('PHP_NULLABLE_TYPE_OUTSIDE_CERTIFIED_SUBSET');
    }
    if ($token->kind !== T_STRING && $token->kind !== T_ARRAY && $token->kind !== T_CALLABLE) {
        fail($code, is_int($token->kind) ? token_name($token->kind) : $token->kind);
    }
    $cursor->next();
    $following = $cursor->peek();
    if ($following !== null && ($following->kind === '|' || $following->kind === '&')) {
        fail('PHP_UNION_TYPE_OUTSIDE_CERTIFIED_SUBSET');
    }
    $spelling = strtolower($token->text);
    if (!array_key_exists($spelling, CANONICAL_TYPES)) {
        fail('PHP_UNSUPPORTED_TYPE', $token->text);
    }
    return CANONICAL_TYPES[$spelling];
}

function parseParameters(Cursor $cursor): array
{
    $cursor->expect('(', 'PHP_UNSUPPORTED_STATEMENT');
    $parameters = [];
    if ($cursor->peek() !== null && $cursor->peek()->kind === ')') {
        $cursor->next();
        return $parameters;
    }
    while (true) {
        $token = $cursor->peek();
        if ($token === null) {
            fail('PHP_UNEXPECTED_END_OF_INPUT');
        }
        if ($token->kind === '&' || $token->kind === T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG) {
            fail('PHP_BY_REFERENCE_PARAMETER_OUTSIDE_CERTIFIED_SUBSET');
        }
        if ($token->kind === T_ELLIPSIS) {
            fail('PHP_VARIADIC_PARAMETER_OUTSIDE_CERTIFIED_SUBSET');
        }
        if (in_array($token->kind, [T_PUBLIC, T_PRIVATE, T_PROTECTED, T_READONLY], true)) {
            fail('PHP_UNSUPPORTED_STATEMENT', 'promoted-property');
        }
        if ($token->kind === T_VARIABLE) {
            fail('PHP_EXPLICIT_PARAMETER_TYPE_REQUIRED', $token->text);
        }
        $start = $token->start;
        $type = canonicalType($cursor, 'PHP_EXPLICIT_PARAMETER_TYPE_REQUIRED');
        $after = $cursor->peek();
        // `int &$a` puts the by-reference marker *after* the type, so this is
        // the position that actually catches it; the pre-type check above only
        // catches the untyped `&$a` spelling.
        if ($after !== null
            && ($after->kind === '&' || $after->kind === T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG)
        ) {
            fail('PHP_BY_REFERENCE_PARAMETER_OUTSIDE_CERTIFIED_SUBSET');
        }
        if ($after !== null && $after->kind === T_ELLIPSIS) {
            fail('PHP_VARIADIC_PARAMETER_OUTSIDE_CERTIFIED_SUBSET');
        }
        $variable = $cursor->expect(T_VARIABLE, 'PHP_UNSUPPORTED_STATEMENT');
        if ($cursor->peek() !== null && $cursor->peek()->kind === '=') {
            fail('PHP_DEFAULT_ARGUMENT_OUTSIDE_CERTIFIED_SUBSET', $variable->text);
        }
        $parameters[] = [
            'name' => substr($variable->text, 1),
            'type' => $type,
            'source_span' => span($cursor->file(), $start, $variable->end),
        ];
        if ($cursor->accept(',') !== null) {
            continue;
        }
        $cursor->expect(')', 'PHP_UNSUPPORTED_STATEMENT');
        return $parameters;
    }
}

function literalNode(Cursor $cursor, Tok $token): array
{
    $kind = $token->kind;
    if ($kind === T_LNUMBER) {
        $text = str_replace('_', '', $token->text);
        // 0x/0b/0o and the legacy leading-zero octal all lex as T_LNUMBER. They
        // denote the same values decimal does, but round-tripping them through
        // the IR would silently rewrite the literal's spelling, so they are a
        // refusal rather than a normalisation.
        if (!preg_match('/\A(?:0|[1-9][0-9]*)\z/', $text)) {
            fail('PHP_UNSUPPORTED_EXPRESSION', 'non-decimal-integer-literal');
        }
        // An integer literal in PHP that does not fit the int range is silently
        // a float, so the range check is a type question, not a style one.
        if (bccomp_fallback($text, '9223372036854775807') > 0) {
            fail('PHP_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE', $text);
        }
        return ['kind' => 'literal', 'value' => (int) $text, 'source_span' => span($cursor->file(), $token->start, $token->end)];
    }
    if ($kind === T_DNUMBER) {
        $text = str_replace('_', '', $token->text);
        // PHP's lexer promotes an integer literal that does not fit the int
        // range to T_DNUMBER, so an all-digit T_DNUMBER is an integer literal
        // that already overflowed. Accepting it would put a float into a
        // position the canonical lattice types as `integer`.
        if (preg_match('/\A[0-9]+\z/', $text)) {
            fail('PHP_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE', $text);
        }
        $value = (float) $text;
        if (!is_finite($value)) {
            fail('PHP_UNSUPPORTED_FLOAT_LITERAL', $token->text);
        }
        return ['kind' => 'literal', 'value' => $value, 'source_span' => span($cursor->file(), $token->start, $token->end)];
    }
    if ($kind === T_CONSTANT_ENCAPSED_STRING) {
        $quote = $token->text[0];
        $body = substr($token->text, 1, -1);
        if ($quote === "'") {
            $value = str_replace(['\\\\', "\\'"], ['\\', "'"], $body);
        } else {
            // A double-quoted string with no variable and no escape other than
            // the ones below is expressible; anything with interpolation never
            // reaches here because the lexer emits T_ENCAPSED_AND_WHITESPACE.
            if (preg_match('/\\\\[^\\\\"nrtvef0-7xu$]/', $body)) {
                fail('PHP_UNSUPPORTED_EXPRESSION', 'string-escape');
            }
            $value = stripcslashes($body);
        }
        if (!mb_check_encoding($value, 'UTF-8')) {
            fail('PHP_UNSUPPORTED_EXPRESSION', 'non-utf8-string-literal');
        }
        return ['kind' => 'literal', 'value' => $value, 'source_span' => span($cursor->file(), $token->start, $token->end)];
    }
    fail('PHP_UNSUPPORTED_EXPRESSION', is_int($kind) ? token_name($kind) : $kind);
}

/** Compare two non-negative decimal strings without bcmath. */
function bccomp_fallback(string $left, string $right): int
{
    $left = ltrim($left, '0');
    $right = ltrim($right, '0');
    if (strlen($left) !== strlen($right)) {
        return strlen($left) <=> strlen($right);
    }
    return strcmp($left, $right);
}

function parsePrimary(Cursor $cursor, bool $emittedTarget): array
{
    $token = $cursor->next();
    $kind = $token->kind;

    if ($kind === '(') {
        // A cast is `(float)` / `(int)` and the lexer gives it its own token, so
        // a bare `(` here is always a grouping parenthesis.
        $inner = parseExpression($cursor, 0, $emittedTarget);
        $cursor->expect(')', 'PHP_UNSUPPORTED_EXPRESSION');
        return $inner;
    }
    if ($kind === T_VARIABLE) {
        return [
            'kind' => 'name',
            'value' => substr($token->text, 1),
            'source_span' => span($cursor->file(), $token->start, $token->end),
        ];
    }
    if ($kind === T_LNUMBER || $kind === T_DNUMBER || $kind === T_CONSTANT_ENCAPSED_STRING) {
        return literalNode($cursor, $token);
    }
    if ($kind === '"' || $kind === T_ENCAPSED_AND_WHITESPACE || $kind === T_START_HEREDOC) {
        // The lexer only splits a string into these tokens when it interpolates
        // or is a heredoc; a plain literal arrives as T_CONSTANT_ENCAPSED_STRING.
        fail('PHP_STRING_INTERPOLATION_OUTSIDE_CERTIFIED_SUBSET');
    }
    if ($kind === '-' || $kind === '+') {
        // Unary sign on a numeric literal only: the profile has no unary
        // operator node, so anything else is a refusal rather than a rewrite.
        $operand = $cursor->peek();
        if ($operand === null || ($operand->kind !== T_LNUMBER && $operand->kind !== T_DNUMBER)) {
            fail('PHP_UNSUPPORTED_EXPRESSION', 'unary-operator');
        }
        $cursor->next();
        $literal = literalNode($cursor, $operand);
        if ($kind === '-') {
            $literal['value'] = -$literal['value'];
            if (is_int($literal['value']) === false && is_float($literal['value']) === false) {
                fail('PHP_UNSUPPORTED_EXPRESSION', 'unary-operator');
            }
        }
        $literal['source_span'] = span($cursor->file(), $token->start, $operand->end);
        return $literal;
    }
    if ($kind === T_DOUBLE_CAST || $kind === T_INT_CAST) {
        if (!$emittedTarget) {
            fail('PHP_UNSUPPORTED_EXPRESSION', 'cast');
        }
        // `(float)($x)` is the widening the emitter inserts before a strict
        // comparison of an integer against a number. The canonical IR has no
        // cast node because every other target performs the same widening
        // implicitly, so the cast is transparent on relift.
        return parseUnaryOperand($cursor, $emittedTarget);
    }
    if ($kind === T_NAME_FULLY_QUALIFIED || $kind === T_NAME_QUALIFIED || $kind === T_NAME_RELATIVE) {
        fail('PHP_QUALIFIED_NAME_OUTSIDE_CERTIFIED_SUBSET', $token->text);
    }
    if ($kind === T_STRING) {
        $lowered = strtolower($token->text);
        if ($lowered === 'true' || $lowered === 'false') {
            return [
                'kind' => 'literal',
                'value' => $lowered === 'true',
                'source_span' => span($cursor->file(), $token->start, $token->end),
            ];
        }
        if ($lowered === 'php_int_min') {
            return [
                'kind' => 'literal',
                'value' => PHP_INT_MIN,
                'source_span' => span($cursor->file(), $token->start, $token->end),
            ];
        }
        if ($lowered === 'php_int_max') {
            return [
                'kind' => 'literal',
                'value' => PHP_INT_MAX,
                'source_span' => span($cursor->file(), $token->start, $token->end),
            ];
        }
        return parseCall($cursor, $token, $emittedTarget);
    }
    fail('PHP_UNSUPPORTED_EXPRESSION', is_int($kind) ? token_name($kind) : $kind);
}

function parseUnaryOperand(Cursor $cursor, bool $emittedTarget): array
{
    return parsePrimary($cursor, $emittedTarget);
}

function parseCall(Cursor $cursor, Tok $name, bool $emittedTarget): array
{
    $lowered = strtolower($name->text);
    if (!$emittedTarget) {
        fail('PHP_CALL_OUTSIDE_CERTIFIED_SUBSET', $name->text);
    }
    $cursor->expect('(', 'PHP_UNSUPPORTED_EXPRESSION');
    $arguments = [];
    if ($cursor->peek() !== null && $cursor->peek()->kind === ')') {
        $cursor->next();
    } else {
        while (true) {
            $arguments[] = parseExpression($cursor, 0, $emittedTarget);
            if ($cursor->accept(',') !== null) {
                continue;
            }
            $cursor->expect(')', 'PHP_UNSUPPORTED_EXPRESSION');
            break;
        }
    }
    $close = $cursor->peek(-1);
    $end = $close === null ? $name->end : $close->end;
    if (in_array($lowered, EMITTED_IDENTITY_HELPERS, true)) {
        if (count($arguments) !== 1) {
            fail('PHP_EMITTED_HELPER_ARITY_INVALID', $name->text);
        }
        return $arguments[0];
    }
    if (array_key_exists($lowered, EMITTED_BINARY_HELPERS)) {
        if (count($arguments) !== 2) {
            fail('PHP_EMITTED_HELPER_ARITY_INVALID', $name->text);
        }
        return [
            'kind' => 'binary',
            'operator' => EMITTED_BINARY_HELPERS[$lowered],
            'left' => $arguments[0],
            'right' => $arguments[1],
            'source_span' => span($cursor->file(), $name->start, $end),
            // Internal marker, stripped before output. A node produced by
            // folding one of the emitter's helper calls is canonical by
            // construction: `elmos_checked_div` *is* the truncating integer
            // division and `fmod` *is* the float remainder, so the two
            // operator-spelling refusals in `inferType` -- which exist to catch
            // a raw `/` or `%` written by hand -- must not fire on it.
            '_helper_folded' => true,
        ];
    }
    fail('PHP_CALL_OUTSIDE_CERTIFIED_SUBSET', $name->text);
}

function operatorText(?Tok $token): ?string
{
    if ($token === null) {
        return null;
    }
    if (is_string($token->kind)) {
        return in_array($token->kind, ['+', '-', '*', '/', '%', '<', '>', '.'], true) ? $token->kind : null;
    }
    return match ($token->kind) {
        T_IS_IDENTICAL => '===',
        T_IS_NOT_IDENTICAL => '!==',
        T_IS_SMALLER_OR_EQUAL => '<=',
        T_IS_GREATER_OR_EQUAL => '>=',
        T_BOOLEAN_AND => '&&',
        T_BOOLEAN_OR => '||',
        T_IS_EQUAL => 'LOOSE_EQUAL',
        T_IS_NOT_EQUAL => 'LOOSE_NOT_EQUAL',
        T_LOGICAL_AND => 'WORD_AND',
        T_LOGICAL_OR => 'WORD_OR',
        default => null,
    };
}

function parseExpression(Cursor $cursor, int $minimumPrecedence, bool $emittedTarget): array
{
    $left = parsePrimary($cursor, $emittedTarget);
    while (true) {
        $operator = operatorText($cursor->peek());
        if ($operator === null) {
            return $left;
        }
        if ($operator === 'LOOSE_EQUAL' || $operator === 'LOOSE_NOT_EQUAL') {
            // `==` on two strings is `'1' == '01'` -> true. The canonical `==`
            // is value equality, which in PHP is spelled `===`.
            fail('PHP_LOOSE_COMPARISON_OUTSIDE_CERTIFIED_SUBSET', $operator === 'LOOSE_EQUAL' ? '==' : '!=');
        }
        if ($operator === 'WORD_AND' || $operator === 'WORD_OR') {
            // `and`/`or` bind looser than `=`; admitting them would make the
            // lifted tree's shape depend on a precedence rule no other target
            // has.
            fail('PHP_UNSUPPORTED_OPERATOR', $operator === 'WORD_AND' ? 'and' : 'or');
        }
        $precedence = PRECEDENCE[$operator] ?? null;
        if ($precedence === null || $precedence < $minimumPrecedence) {
            return $left;
        }
        $token = $cursor->next();
        // Every admitted operator is left-associative, so the right operand is
        // parsed at one level tighter.
        $right = parseExpression($cursor, $precedence + 1, $emittedTarget);
        if ($operator === '/') {
            // Whether a literal `/` is the canonical division depends on the
            // operand types, which are not known until the whole function is
            // typed. `checkOperandTypes` below decides it; see the note there.
            $canonical = '/';
        } elseif ($operator === '.') {
            $canonical = '+';
        } else {
            $canonical = BINARY_OPERATORS[$operator] ?? null;
        }
        if ($canonical === null) {
            fail('PHP_UNSUPPORTED_OPERATOR', $operator);
        }
        $left = [
            'kind' => 'binary',
            'operator' => $canonical,
            'left' => $left,
            'right' => $right,
            'source_span' => span(
                $cursor->file(),
                $left['source_span']['start_byte'],
                $right['source_span']['end_byte'],
            ),
        ];
    }
}

function parseBlock(Cursor $cursor, bool $emittedTarget): array
{
    $cursor->expect('{', 'PHP_UNSUPPORTED_STATEMENT');
    $statements = [];
    while (true) {
        $token = $cursor->peek();
        if ($token === null) {
            fail('PHP_UNEXPECTED_END_OF_INPUT');
        }
        if ($token->kind === '}') {
            $cursor->next();
            return $statements;
        }
        $statements[] = parseStatement($cursor, $emittedTarget);
    }
}

/**
 * Consume one brace-balanced block without interpreting it.
 *
 * Used only for the emitter's own helper bodies under --emitted-target. Their
 * contents (`throw`, assignment, `!is_int(...)`) are deliberately outside the
 * lifted subset, and they do not need to be lifted: `native._verify_emitted_
 * helper_sources` has already asserted that each helper's source text appears
 * byte-for-byte exactly once in this file, so the body is fixed by that check
 * rather than by re-parsing it here. Skipping is therefore not a hole -- the
 * bytes are pinned somewhere stronger.
 */
function skipBalancedBlock(Cursor $cursor): Tok
{
    $cursor->expect('{', 'PHP_UNSUPPORTED_STATEMENT');
    $depth = 1;
    while (true) {
        $token = $cursor->next();
        if ($token->kind === '{' || $token->kind === T_CURLY_OPEN || $token->kind === T_DOLLAR_OPEN_CURLY_BRACES) {
            $depth++;
        } elseif ($token->kind === '}') {
            $depth--;
            if ($depth === 0) {
                return $token;
            }
        }
    }
}


function parseStatement(Cursor $cursor, bool $emittedTarget): array
{
    $token = $cursor->peek();
    if ($token === null) {
        fail('PHP_UNEXPECTED_END_OF_INPUT');
    }
    if ($token->kind === T_RETURN) {
        $cursor->next();
        if ($cursor->peek() !== null && $cursor->peek()->kind === ';') {
            fail('PHP_RETURN_WITHOUT_VALUE');
        }
        $expression = parseExpression($cursor, 0, $emittedTarget);
        $semicolon = $cursor->expect(';', 'PHP_UNSUPPORTED_STATEMENT');
        return [
            'kind' => 'return',
            'expression' => $expression,
            'source_span' => span($cursor->file(), $token->start, $semicolon->end),
        ];
    }
    if ($token->kind === T_IF) {
        $cursor->next();
        $cursor->expect('(', 'PHP_UNSUPPORTED_CONDITION');
        $condition = parseExpression($cursor, 0, $emittedTarget);
        $cursor->expect(')', 'PHP_UNSUPPORTED_CONDITION');
        $then = parseBlock($cursor, $emittedTarget);
        $else = [];
        $end = $cursor->peek(-1);
        if ($cursor->peek() !== null && $cursor->peek()->kind === T_ELSEIF) {
            // `elseif` is expressible as a nested `if`, but rewriting it would
            // make the emitted shape differ from the source shape for no gain.
            fail('PHP_UNSUPPORTED_STATEMENT', 'elseif');
        }
        if ($cursor->peek() !== null && $cursor->peek()->kind === T_ELSE) {
            $cursor->next();
            if ($cursor->peek() !== null && $cursor->peek()->kind === T_IF) {
                fail('PHP_UNSUPPORTED_STATEMENT', 'else-if');
            }
            $else = parseBlock($cursor, $emittedTarget);
            $end = $cursor->peek(-1);
        }
        return [
            'kind' => 'if',
            'condition' => $condition,
            'then' => $then,
            'else' => $else,
            'source_span' => span($cursor->file(), $token->start, $end === null ? $token->end : $end->end),
        ];
    }
    fail('PHP_UNSUPPORTED_STATEMENT', is_int($token->kind) ? token_name($token->kind) : $token->kind);
}


/**
 * Canonical type of one lifted expression, or a refusal.
 *
 * This is deliberately the same closed, total lattice `types.infer` implements
 * on the Python side, restated here because two PHP operators cannot be judged
 * without it:
 *
 *   * `/` is the canonical division on two floats, and is *not* the canonical
 *     truncating division on two ints -- PHP answers 3.5 for `7 / 2`, and the
 *     result is not even an int. The truncating form is `intdiv`, which only
 *     appears in emitted target source.
 *   * `%` is an integer operator that silently casts float operands to int, so
 *     `7.5 % 2` is 1. The float remainder is `fmod`.
 *
 * Refusing them unconditionally would reject valid float division; accepting
 * them unconditionally would lift two different operators onto one IR node.
 */
function inferType(array $node, array $environment): string
{
    if ($node['kind'] === 'name') {
        $name = $node['value'];
        if (!array_key_exists($name, $environment)) {
            fail('PHP_UNDECLARED_NAME', $name);
        }
        return $environment[$name];
    }
    if ($node['kind'] === 'literal') {
        $value = $node['value'];
        if (is_bool($value)) {
            return 'boolean';
        }
        if (is_int($value)) {
            return 'integer';
        }
        if (is_float($value)) {
            return 'number';
        }
        if (is_string($value)) {
            return 'string';
        }
        fail('PHP_UNSUPPORTED_EXPRESSION', 'literal');
    }
    $operator = $node['operator'];
    $left = inferType($node['left'], $environment);
    $right = inferType($node['right'], $environment);
    $numeric = ['integer' => true, 'number' => true];
    if (in_array($operator, ['+', '-', '*', '/', '%'], true)) {
        if ($operator === '+' && $left === 'string' && $right === 'string') {
            return 'string';
        }
        if (!isset($numeric[$left]) || !isset($numeric[$right])) {
            fail('PHP_OPERAND_TYPE_MISMATCH', "$operator:$left:$right");
        }
        $folded = $node['_helper_folded'] ?? false;
        if (!$folded && $operator === '/' && $left === 'integer' && $right === 'integer') {
            fail('PHP_INTEGER_DIVISION_OUTSIDE_CERTIFIED_SUBSET');
        }
        if (!$folded && $operator === '%' && ($left === 'number' || $right === 'number')) {
            fail('PHP_FLOAT_REMAINDER_OUTSIDE_CERTIFIED_SUBSET');
        }
        return ($left === 'number' || $right === 'number') ? 'number' : 'integer';
    }
    if (in_array($operator, ['<', '<=', '>', '>='], true)) {
        if ($left === 'string' || $right === 'string') {
            fail('PHP_STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET', $operator);
        }
        if (!isset($numeric[$left]) || !isset($numeric[$right])) {
            fail('PHP_OPERAND_TYPE_MISMATCH', "$operator:$left:$right");
        }
        return 'boolean';
    }
    if ($operator === '==' || $operator === '!=') {
        if ($left !== $right && !(isset($numeric[$left]) && isset($numeric[$right]))) {
            fail('PHP_OPERAND_TYPE_MISMATCH', "$operator:$left:$right");
        }
        return 'boolean';
    }
    if ($operator === '&&' || $operator === '||') {
        if ($left !== 'boolean' || $right !== 'boolean') {
            fail('PHP_OPERAND_TYPE_MISMATCH', "$operator:$left:$right");
        }
        return 'boolean';
    }
    fail('PHP_UNSUPPORTED_OPERATOR', $operator);
}

function checkStatements(array $statements, array $environment, string $returnType): void
{
    foreach ($statements as $statement) {
        if ($statement['kind'] === 'return') {
            $actual = inferType($statement['expression'], $environment);
            if ($actual !== $returnType && !($actual === 'integer' && $returnType === 'number')) {
                fail('PHP_RETURN_TYPE_MISMATCH', "$returnType:$actual");
            }
            continue;
        }
        if (inferType($statement['condition'], $environment) !== 'boolean') {
            fail('PHP_CONDITION_MUST_BE_BOOLEAN');
        }
        checkStatements($statement['then'], $environment, $returnType);
        checkStatements($statement['else'], $environment, $returnType);
    }
}

function checkOperandTypes(array $function): void
{
    $environment = [];
    foreach ($function['parameters'] as $parameter) {
        if (array_key_exists($parameter['name'], $environment)) {
            fail('PHP_DUPLICATE_PARAMETER', $parameter['name']);
        }
        $environment[$parameter['name']] = $parameter['type'];
    }
    checkStatements($function['body'], $environment, $function['return_type']);
}


/**
 * Walk the file and lift the requested function.
 *
 * Every other top-level construct is refused rather than skipped: a `class`, a
 * `namespace`, a side-effecting statement or an `include` next to the subject
 * changes what loading the file does, and the profile's claim is about the file
 * as a whole, not about one function read out of it.
 */
function lift(Cursor $cursor, string $functionName, bool $emittedTarget): array
{
    requireStrictTypes($cursor);
    acceptNamespace($cursor);
    $found = null;
    $declaredNames = [];
    while (!$cursor->atEnd()) {
        $token = $cursor->peek();
        if ($token->kind !== T_FUNCTION) {
            fail('PHP_UNSUPPORTED_STATEMENT', is_int($token->kind) ? token_name($token->kind) : $token->kind);
        }
        $start = $cursor->next()->start;
        if ($cursor->peek() !== null && $cursor->peek()->kind === '&') {
            fail('PHP_REFERENCE_RETURN_OUTSIDE_CERTIFIED_SUBSET');
        }
        $nameToken = $cursor->peek();
        if ($nameToken === null || $nameToken->kind !== T_STRING) {
            fail('PHP_CLOSURE_OUTSIDE_CERTIFIED_SUBSET');
        }
        $cursor->next();
        $declared = $nameToken->text;
        $folded = strtolower($declared);
        if (isset($declaredNames[$folded])) {
            // PHP resolves function names case-insensitively, so this file
            // could not be loaded at all.
            fail('PHP_DUPLICATE_FUNCTION_NAME', $declared);
        }
        $declaredNames[$folded] = true;
        $parameters = parseParameters($cursor);
        $colon = $cursor->peek();
        if ($colon === null || $colon->kind !== ':') {
            fail('PHP_EXPLICIT_RETURN_TYPE_REQUIRED', $declared);
        }
        $cursor->next();
        $returnType = canonicalType($cursor, 'PHP_EXPLICIT_RETURN_TYPE_REQUIRED');
        if ($emittedTarget
            && in_array($folded, EMITTED_HELPER_NAMES, true)
            && $folded !== strtolower($functionName)
        ) {
            skipBalancedBlock($cursor);
            continue;
        }
        $body = parseBlock($cursor, $emittedTarget);
        $closing = $cursor->peek(-1);
        if ($folded === strtolower($functionName)) {
            if ($found !== null) {
                fail('PHP_DUPLICATE_FUNCTION_NAME', $declared);
            }
            $found = [
                'name' => $declared,
                'parameters' => $parameters,
                'return_type' => $returnType,
                'body' => $body,
                'source_span' => span($cursor->file(), $start, $closing === null ? $start + 1 : $closing->end),
            ];
        } elseif (!in_array($folded, EMITTED_HELPER_NAMES, true) && !$emittedTarget) {
            // A sibling function is allowed: the module profile lifts several
            // from one file. It still has to be inside the subset, which the
            // parse above already enforced.
            continue;
        }
    }
    if ($found === null) {
        fail('PHP_FUNCTION_NOT_FOUND', $functionName);
    }
    if ($found['body'] === []) {
        fail('PHP_FUNCTION_BODY_REQUIRED', $functionName);
    }
    checkOperandTypes($found);
    return $found;
}

/**
 * Optional third witness: compare the lifted shape against Zend's own AST.
 *
 * Only ever refuses. The comparison is deliberately structural -- the function
 * name, each parameter's name and declared type, the return type, and the
 * sequence of statement kinds -- rather than a second full lift, because the
 * value here is catching a *disagreement about what the compiler saw*, not
 * re-deriving the IR twice and having to keep two derivations in step.
 *
 * The extension is optional but the version is not: if `ast` is loaded and does
 * not support the pinned AST version, that is a configuration error and fails
 * closed, because the node shapes this function reads are version-dependent.
 * An absent extension is a documented weaker mode; a present but unusable one
 * is not.
 *
 * Note this only fires when `ast` is compiled into the pinned build. The engine
 * invokes PHP with `-n`, which drops every php.ini, so a PECL install activated
 * through an ini file is deliberately invisible: an analysis result must not
 * depend on configuration the toolchain pin does not cover.
 */
function crossCheckWithZendAst(string $path, array $function): ?array
{
    if (!extension_loaded('ast')) {
        return null;
    }
    if (!in_array(PHP_AST_VERSION, \ast\get_supported_versions(), true)) {
        fail('PHP_ZEND_AST_VERSION_UNSUPPORTED', (string) PHP_AST_VERSION);
    }
    try {
        $root = \ast\parse_file($path, PHP_AST_VERSION);
    } catch (\Throwable $error) {
        fail('PHP_ZEND_AST_PARSE_FAILED', $error->getMessage());
    }
    $subject = null;
    foreach ($root->children as $node) {
        if (!$node instanceof \ast\Node || \ast\get_kind_name($node->kind) !== 'AST_FUNC_DECL') {
            continue;
        }
        if (strtolower((string) ($node->children['name'] ?? '')) === strtolower($function['name'])) {
            if ($subject !== null) {
                fail('PHP_ZEND_AST_SUBJECT_AMBIGUOUS', $function['name']);
            }
            $subject = $node;
        }
    }
    if ($subject === null) {
        fail('PHP_ZEND_AST_SUBJECT_MISSING', $function['name']);
    }

    $observed = [];
    foreach ($subject->children['params']->children as $parameter) {
        $observed[] = [
            'name' => (string) $parameter->children['name'],
            'type' => zendTypeToCanonical($parameter->children['type'] ?? null),
        ];
    }
    $lifted = [];
    foreach ($function['parameters'] as $parameter) {
        $lifted[] = ['name' => $parameter['name'], 'type' => $parameter['type']];
    }
    if ($observed !== $lifted) {
        fail(
            'PHP_ZEND_AST_PARAMETER_MISMATCH',
            $function['name'] . ':' . json_encode($observed) . ':' . json_encode($lifted),
        );
    }

    $returnType = zendTypeToCanonical($subject->children['returnType'] ?? null);
    if ($returnType !== $function['return_type']) {
        fail(
            'PHP_ZEND_AST_RETURN_TYPE_MISMATCH',
            $function['name'] . ':' . (string) $returnType . ':' . $function['return_type'],
        );
    }

    $observedKinds = [];
    foreach ($subject->children['stmts']->children as $statement) {
        $observedKinds[] = $statement instanceof \ast\Node
            ? \ast\get_kind_name($statement->kind)
            : 'NON_NODE';
    }
    $liftedKinds = array_map(
        static fn(array $statement): string => $statement['kind'] === 'return' ? 'AST_RETURN' : 'AST_IF',
        $function['body'],
    );
    if ($observedKinds !== $liftedKinds) {
        fail(
            'PHP_ZEND_AST_STATEMENT_SHAPE_MISMATCH',
            $function['name'] . ':' . implode(',', $observedKinds) . ':' . implode(',', $liftedKinds),
        );
    }
    return ['version' => PHP_AST_VERSION, 'statements' => count($observedKinds)];
}

/**
 * Canonical type of one Zend AST type node, or a refusal.
 *
 * A scalar type arrives as an AST_TYPE node whose `flags` name the type. A
 * class type is an AST_NAME, a union is AST_TYPE_UNION, an intersection is
 * AST_TYPE_INTERSECTION, and nullability sets a bit on the flags -- none of
 * which the profile admits, and all of which the tokenizer lift has already
 * refused, so reaching one here means the two frontends disagree.
 */
function zendTypeToCanonical(mixed $node): ?string
{
    if (!$node instanceof \ast\Node) {
        return null;
    }
    if (\ast\get_kind_name($node->kind) !== 'AST_TYPE') {
        return null;
    }
    return match ($node->flags) {
        ZEND_TYPE_LONG => 'integer',
        ZEND_TYPE_DOUBLE => 'number',
        ZEND_TYPE_BOOL => 'boolean',
        ZEND_TYPE_STRING => 'string',
        default => null,
    };
}

/** Remove every internal marker; the IR schema rejects unknown keys. */
function stripInternal(mixed $node): mixed
{
    if (!is_array($node)) {
        return $node;
    }
    $out = [];
    foreach ($node as $key => $value) {
        if (is_string($key) && str_starts_with($key, '_')) {
            continue;
        }
        $out[$key] = stripInternal($value);
    }
    return $out;
}


function main(array $argv): int
{
    if (count($argv) < 3) {
        fwrite(STDERR, "usage: analyzer.php <source-path> <function-name> [--emitted-target]\n");
        return 2;
    }
    if (!function_exists('token_get_all')) {
        // The engine runs PHP with `-n`, and a build that ships ext/tokenizer as
        // a shared module loses it with the ini. The toolchain pin is supposed to
        // re-add it by absolute path; landing here means that binding is wrong.
        fwrite(STDERR, "PHP_TOKENIZER_EXTENSION_MISSING\n");
        return 1;
    }
    $path = $argv[1];
    $functionName = $argv[2];
    $emittedTarget = in_array('--emitted-target', array_slice($argv, 3), true);

    if (!is_file($path) || is_link($path)) {
        fwrite(STDERR, "PHP_ANALYZER_SOURCE_UNSAFE\n");
        return 1;
    }
    $size = filesize($path);
    if ($size === false || $size > MAX_SOURCE_BYTES) {
        fwrite(STDERR, "PHP_ANALYZER_SOURCE_UNSAFE\n");
        return 1;
    }
    $source = file_get_contents($path);
    if ($source === false) {
        fwrite(STDERR, "PHP_ANALYZER_SOURCE_UNSAFE\n");
        return 1;
    }

    try {
        $tokens = significant(lex($source));
        $cursor = new Cursor($tokens, basename($path));
        $function = lift($cursor, $functionName, $emittedTarget);
        $witness = crossCheckWithZendAst($path, $function);
        $function = stripInternal($function);
    } catch (DomainError $error) {
        fwrite(STDERR, $error->getMessage() . "\n");
        return 1;
    }

    $analyzerVersion = 'php-' . PHP_VERSION . ';tokenizer=' . phpversion('tokenizer');
    $analyzerVersion .= ';zend-ast=' . ($witness === null ? 'ABSENT' : 'v' . $witness['version']);

    echo json_encode(
        [
            'schema_version' => SCHEMA_VERSION,
            'source_language' => 'php',
            'source_file' => basename($path),
            'analyzer' => ANALYZER_NAME,
            'analyzer_version' => $analyzerVersion,
            'functions' => [$function],
            'diagnostics' => [],
        ],
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION,
    ), "\n";
    return 0;
}

exit(main($argv));
