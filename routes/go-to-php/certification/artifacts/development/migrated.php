<?php

declare(strict_types=1);

function elmos_checked_add(int $left, int $right): int {
    $result = $left + $right;
    if (!is_int($result)) {
        throw new \ArithmeticError('ELMOS_INTEGER_OVERFLOW');
    }
    return $result;
}

function calculate(int $subtotal, int $tax): int {
    if (($subtotal < 0)) {
        return 0;
    }
    return elmos_checked_add($subtotal, $tax);
}
