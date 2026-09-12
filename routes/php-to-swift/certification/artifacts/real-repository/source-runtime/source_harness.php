<?php

declare(strict_types=1);

require __DIR__ . '/difference.php';

function elmos_harness_same_fp64(float $left, float $right): bool {
    if (is_nan($left) && is_nan($right)) {
        return true;
    }
    return pack('E', $left) === pack('E', $right);
}

function elmos_harness_fp64(float $value): string {
    return bin2hex(pack('E', $value));
}

$actual_0 = difference(20, 7);
$expected_0 = 13;
if ($actual_0 !== $expected_0) { fwrite(STDERR, 'case 0' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t0\ti64-dec\t", (string)$actual_0, PHP_EOL;
$actual_1 = difference(3, 8);
$expected_1 = 0;
if ($actual_1 !== $expected_1) { fwrite(STDERR, 'case 1' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t1\ti64-dec\t", (string)$actual_1, PHP_EOL;
$actual_2 = difference(4, 4);
$expected_2 = 0;
if ($actual_2 !== $expected_2) { fwrite(STDERR, 'case 2' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t2\ti64-dec\t", (string)$actual_2, PHP_EOL;
