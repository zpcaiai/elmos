package holdout

fun clamp(value: Long, upper: Long): Long {
    if (value > upper) {
        return upper
    }
    if (value < 0L) {
        return 0L
    }
    return value
}
