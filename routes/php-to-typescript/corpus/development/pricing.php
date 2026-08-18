<?php

declare(strict_types=1);

function calculate(int $subtotal, int $tax): int {
    if ($subtotal < 0) {
        return 0;
    }
    return $subtotal + $tax;
}
