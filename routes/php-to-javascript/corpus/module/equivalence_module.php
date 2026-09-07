<?php

declare(strict_types=1);

function calculate(int $subtotal, int $tax): int {
    if ($subtotal < 0) { return 0; }
    return $subtotal + $tax;
}

function clamp(int $value, int $minimum, int $maximum): int {
    if ($value < $minimum) { return $minimum; }
    if ($value > $maximum) { return $maximum; }
    return $value;
}

function difference(int $left, int $right): int { return $left - $right; }

function clampNumber(float $value, float $minimum, float $maximum): float {
    if ($value < $minimum) { return $minimum; }
    if ($value > $maximum) { return $maximum; }
    return $value;
}

function both(bool $left, bool $right): bool { return $left && $right; }
