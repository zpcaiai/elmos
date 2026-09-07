<?php

/**
 * Assert every PHP behaviour the emitter's compensations depend on.
 *
 * The PHP arms in `emitter.py` were written against measurements, not against
 * the manual, and the README states the version those measurements were taken
 * on. This script is that measurement in executable form, so the claim can be
 * re-checked on any build rather than trusted because it was true once.
 *
 * Run it against the interpreter you are about to pin:
 *
 *     php -n tools/verify_php_semantics.php
 *
 * Exit status is 0 when every assertion holds and 1 otherwise, and a failure
 * names the emitter arm that assumed it. A failure here does not mean PHP is
 * broken; it means an emitter arm is compensating for behaviour this build does
 * not have, and the arm has to be re-derived before the route is trustworthy.
 */

declare(strict_types=1);

$failures = [];
$checked = 0;

function check(string $claim, string $arm, callable $probe, mixed $expected): void
{
    global $failures, $checked;
    $checked++;
    try {
        $observed = $probe();
    } catch (\Throwable $error) {
        $observed = get_class($error);
    }
    if ($observed !== $expected) {
        $failures[] = [
            'claim' => $claim,
            'arm' => $arm,
            'expected' => var_export($expected, true),
            'observed' => var_export($observed, true),
        ];
    }
}

// --- the build itself -------------------------------------------------------
check('PHP_INT_SIZE is 8', 'toolchains._php_runtime_identity', fn() => PHP_INT_SIZE, 8);
check('PHP_INT_MAX is 2^63-1', 'emitter._TYPE_SPELLING integer', fn() => PHP_INT_MAX, 9223372036854775807);
check('PHP_INT_MIN is -2^63', 'emitter._integer_literal', fn() => PHP_INT_MIN, -9223372036854775807 - 1);
check('float is binary64', 'toolchains._php_runtime_identity', fn() => PHP_FLOAT_DIG, 15);

// --- R1: overflow promotes to float, and that is the only signal ------------
check(
    'PHP_INT_MAX + 1 is a float, not a wrap and not an error',
    'emitter._PHP_HELPERS checked_add',
    fn() => is_float(PHP_INT_MAX + 1),
    true,
);
check(
    'PHP_INT_MIN - 1 is a float',
    'emitter._PHP_HELPERS checked_sub',
    fn() => is_float(PHP_INT_MIN - 1),
    true,
);
check(
    'PHP_INT_MAX * 2 is a float',
    'emitter._PHP_HELPERS checked_mul',
    fn() => is_float(PHP_INT_MAX * 2),
    true,
);
check(
    'an in-range int result stays an int, so is_int is exact and not a heuristic',
    'emitter._PHP_HELPERS checked_add',
    fn() => is_int((PHP_INT_MAX - 1) + 1),
    true,
);

// --- R2: division and remainder --------------------------------------------
check('intdiv truncates toward zero', 'emitter._PHP_HELPERS checked_div', fn() => intdiv(-7, 2), -3);
check(
    'intdiv by zero raises DivisionByZeroError',
    'emitter._PHP_HELPERS checked_div',
    fn() => intdiv(7, 0),
    'DivisionByZeroError',
);
check(
    'intdiv(PHP_INT_MIN, -1) raises ArithmeticError',
    'emitter._PHP_HELPERS checked_div',
    fn() => intdiv(PHP_INT_MIN, -1),
    'ArithmeticError',
);
check('% truncates toward zero', 'emitter._PHP_HELPERS checked_mod', fn() => -7 % 2, -1);
check(
    '% by zero raises DivisionByZeroError',
    'emitter._PHP_HELPERS checked_mod',
    fn() => 7 % 0,
    'DivisionByZeroError',
);
check(
    'PHP_INT_MIN % -1 answers 0 instead of failing -- this arm is a real guard',
    'emitter._PHP_HELPERS checked_mod',
    fn() => PHP_INT_MIN % -1,
    0,
);

// --- the four operators whose obvious emission is wrong ---------------------
check(
    '/ on two ints is NOT truncating division',
    'emitter._binary integer /',
    fn() => 7 / 2,
    3.5,
);
check(
    '/ on two ints does not even return an int',
    'emitter._binary integer /',
    fn() => is_float(7 / 2),
    true,
);
check(
    '% casts float operands to int, so it is not the float remainder',
    'emitter._binary number %',
    fn() => @(7.5 % 2),
    1,
);
check(
    'fmod is the truncating float remainder',
    'emitter._binary number % -> fmod',
    fn() => fmod(-7.5, 2.0),
    -1.5,
);
check(
    'fmod by zero answers NAN rather than raising, so it needs the guard',
    'emitter._FLOAT_NON_ZERO_GUARD',
    fn() => is_nan(fmod(7.5, 0.0)),
    true,
);
check(
    'float division by zero raises',
    'emitter._FLOAT_NON_ZERO_GUARD',
    fn() => 1.0 / 0.0,
    'DivisionByZeroError',
);

// --- equality ---------------------------------------------------------------
check("'1' == '01' is true: == type-juggles", 'emitter._binary php equality', fn() => '1' == '01', true);
check("'10' == '1e1' is true: == type-juggles", 'emitter._binary php equality', fn() => '10' == '1e1', true);
check("'1' === '01' is false: === is the value comparison", 'emitter._binary php equality', fn() => '1' === '01', false);
check('1 === 1.0 is false: === compares types too', 'emitter._binary php equality widening', fn() => 1 === 1.0, false);
check('(float)1 === 1.0 is true after widening', 'emitter._binary php equality widening', fn() => (float) 1 === 1.0, true);
check('0.0 === -0.0 is true, matching IEEE ==', 'emitter._binary php equality', fn() => 0.0 === -0.0, true);
check('NAN === NAN is false, matching IEEE ==', 'emitter._binary php equality', fn() => NAN === NAN, false);

// --- strings ----------------------------------------------------------------
check("+ on two strings is a TypeError, so concatenation must emit .", 'emitter._binary php string +', function () {
    $left = '1';
    $right = 'a';
    return $left + $right;
}, 'TypeError');
check("'.' concatenates", 'emitter._binary php string +', fn() => 'a' . 'b', 'ab');
check(
    'a single-quoted string does not interpolate',
    'emitter._string_literal php',
    fn() => 'a$b',
    'a' . chr(36) . 'b',
);
check(
    "a single-quoted string recognises exactly \\\\ and \\'",
    'emitter._string_literal php',
    fn() => 'it\'s\\ok',
    "it's\\ok",
);

// --- literals ---------------------------------------------------------------
check(
    'a bare -9223372036854775808 is a float, so the minimum emits PHP_INT_MIN',
    'emitter._integer_literal php',
    fn() => is_float(-9223372036854775808),
    true,
);
check(
    'an over-range integer literal lexes as a float',
    'native/php/analyzer.php literalNode',
    fn() => is_float(9223372036854775808),
    true,
);
check('PHP_INT_MIN is an int', 'emitter._integer_literal php', fn() => is_int(PHP_INT_MIN), true);

// --- strict_types and widening ---------------------------------------------
check('strict_types still widens int to float for a float parameter', 'emitter._signature php', function () {
    $takes = function (float $value): float { return $value; };
    return $takes(3);
}, 3.0);
check('strict_types refuses float where int is declared', 'emitter._signature php', function () {
    $takes = function (int $value): int { return $value; };
    return $takes(3.0);
}, 'TypeError');

// --- namespace resolution ---------------------------------------------------
check(
    'an unqualified class inside a namespace does NOT fall back to global',
    'emitter._PHP_HELPERS fully qualified class names',
    function () {
        $code = 'namespace Elmos\\Probe; function f() { throw new ArithmeticError("x"); } '
            . 'try { f(); } catch (\\Throwable $e) { return get_class($e); } return "no-throw";';
        return eval($code);
    },
    'Error',
);
check(
    'a fully qualified class inside a namespace resolves',
    'emitter._PHP_HELPERS fully qualified class names',
    function () {
        $code = 'namespace Elmos\\Probe2; function g() { throw new \\ArithmeticError("x"); } '
            . 'try { g(); } catch (\\Throwable $e) { return get_class($e); } return "no-throw";';
        return eval($code);
    },
    'ArithmeticError',
);
check(
    'an unqualified function inside a namespace DOES fall back to global',
    'assembly._place_php namespace injection',
    function () {
        return eval('namespace Elmos\\Probe3; return intdiv(7, 2);');
    },
    3,
);

// --- the observation encodings the harness relies on ------------------------
check('pack E is big-endian binary64', 'validation._php_harness', fn() => bin2hex(pack('E', 1.5)), '3ff8000000000000');
check('-0.0 is distinguishable from 0.0 in the encoding', 'validation._php_harness', fn() => bin2hex(pack('E', -0.0)), '8000000000000000');
check('bin2hex is the hex-utf8 encoding', 'validation._php_harness', fn() => bin2hex('héllo'), '68c3a96c6c6f');

// --- the tokenizer contract the frontend rests on --------------------------
// Skipped rather than failed when ext/tokenizer is absent: under `-n` a build
// that ships it as a shared module has no token_get_all, and the toolchain pin
// re-adds it by absolute path. Running this file plainly (without the pin's
// -d extension=...) is the normal way to hit that, and it is not a divergence.
if (function_exists('token_get_all')) {
check(
    'concatenating every token reproduces the source byte for byte',
    'native/php/analyzer.php lex',
    function () {
        $source = "<?php\n\ndeclare(strict_types=1);\n\nfunction f(int \$a): int { return \$a + 1; }\n";
        $rebuilt = '';
        foreach (token_get_all($source, TOKEN_PARSE) as $token) {
            $rebuilt .= is_array($token) ? $token[1] : $token;
        }
        return $rebuilt === $source;
    },
    true,
);
} else {
    fwrite(STDERR, "note: ext/tokenizer absent under these flags; the token-stream claim was not checked.\n");
}
check(
    'function names resolve case-insensitively',
    'identifier_hygiene php function-role case folding',
    fn() => function_exists('STRLEN'),
    true,
);

printf("PHP %s (%s)\n", PHP_VERSION, PHP_OS_FAMILY);
printf("%d claims checked, %d divergent\n\n", $checked, count($failures));
foreach ($failures as $failure) {
    printf("DIVERGENT: %s\n", $failure['claim']);
    printf("  assumed by: %s\n", $failure['arm']);
    printf("  expected:   %s\n", $failure['expected']);
    printf("  observed:   %s\n\n", $failure['observed']);
}
exit($failures === [] ? 0 : 1);
