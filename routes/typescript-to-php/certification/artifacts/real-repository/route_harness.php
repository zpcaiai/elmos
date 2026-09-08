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

$actual_0 = difference(20.0, 7.0);
$expected_0 = 13.0;
if (!elmos_harness_same_fp64($actual_0, $expected_0)) { fwrite(STDERR, 'case 0' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t0\tfp64-hex\t", elmos_harness_fp64($actual_0), PHP_EOL;
$actual_1 = difference(3.0, 8.0);
$expected_1 = 0.0;
if (!elmos_harness_same_fp64($actual_1, $expected_1)) { fwrite(STDERR, 'case 1' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t1\tfp64-hex\t", elmos_harness_fp64($actual_1), PHP_EOL;
$actual_2 = difference(4.0, 4.0);
$expected_2 = 0.0;
if (!elmos_harness_same_fp64($actual_2, $expected_2)) { fwrite(STDERR, 'case 2' . PHP_EOL); exit(1); }
echo "ELMOS_OBSERVATION\t2\tfp64-hex\t", elmos_harness_fp64($actual_2), PHP_EOL;
