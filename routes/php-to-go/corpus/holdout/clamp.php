<?php

declare(strict_types=1);

function clamp(int $value, int $upper): int {
    if ($value > $upper) {
        return $upper;
    }
    if ($value < 0) {
        return 0;
    }
    return $value;
}
