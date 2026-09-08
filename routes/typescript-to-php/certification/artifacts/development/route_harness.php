<?php

declare(strict_types=1);

require __DIR__ . '/migrated.php';

function elmos_harness_same_fp64(float $left, float $right): bool {
    if (is_nan($left) && is_nan($right)) {
        return true;
    }
    return pack('E', $left) === pack('E', $right);
}

function elmos_harness_fp64(float $value): string {
    return bin2hex(pack('E', $value));
}

$actual_0 = calculate(100.0, 20.0);
$expected_0 = 120.0;
if (!elmos_harness_same_fp64($actual_0, $expected_0)) { fwrite(STDERR, 'case 0' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t0\tfp64-hex\t", elmos_harness_fp64($actual_0), PHP_EOL;
$actual_1 = calculate(-1.0, 5.0);
$expected_1 = 0.0;
if (!elmos_harness_same_fp64($actual_1, $expected_1)) { fwrite(STDERR, 'case 1' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t1\tfp64-hex\t", elmos_harness_fp64($actual_1), PHP_EOL;
$actual_2 = calculate(7.0, -2.0);
$expected_2 = 5.0;
if (!elmos_harness_same_fp64($actual_2, $expected_2)) { fwrite(STDERR, 'case 2' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t2\tfp64-hex\t", elmos_harness_fp64($actual_2), PHP_EOL;
