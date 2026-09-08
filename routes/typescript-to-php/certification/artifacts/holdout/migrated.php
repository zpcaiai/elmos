<?php

declare(strict_types=1);

function clamp(float $value, float $upper): float {
    if (($value > $upper)) {
        return $upper;
    }
    if (($value < 0)) {
        return 0;
    }
    return $value;
}
