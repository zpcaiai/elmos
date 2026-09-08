<?php

declare(strict_types=1);

function elmos_checked_sub(int $left, int $right): int {
    $result = $left - $right;
    if (!is_int($result)) {
        throw new \ArithmeticError('ELMOS_INTEGER_OVERFLOW');
    }
    return $result;
}

function difference(int $left, int $right): int {
    if (($left < $right)) {
        return 0;
    }
    return elmos_checked_sub($left, $right);
}
