# Route cpp-to-php

Declared direction in the eleven-language complete matrix.

Every evidence state in this pack is `NOT_RUN`. Declaring a direction is
not a claim that it has been executed, verified or certified; the pack
records what this direction would have to prove, and the certification
directory is where a run would write what it did prove.

PHP participates in `typed-pure-function-v1` only. Its integer is the
64-bit `int` of a build the toolchain probe has asserted has
`PHP_INT_SIZE == 8`, and its number is binary64. R1 is enforced by the
emitted `elmos_checked_*` helpers, which detect PHP's silent
overflow-to-float promotion; R2 by `intdiv` plus an explicit guard for
`PHP_INT_MIN % -1`, which PHP answers 0 for rather than failing.
