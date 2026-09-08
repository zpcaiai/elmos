<?php

declare(strict_types=1);

function difference(float $left, float $right): float {
    if (($left < $right)) {
        return 0;
    }
    return ($left - $right);
}
