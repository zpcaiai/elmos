<?php

declare(strict_types=1);

function difference(int $left, int $right): int {
    if ($left < $right) {
        return 0;
    }
    return $left - $right;
}
