<?php

declare(strict_types=1);

function calculate(float $subtotal, float $tax): float {
    if (($subtotal < 0)) {
        return 0;
    }
    return ($subtotal + $tax);
}
