package representative

fun difference(left: Long, right: Long): Long {
    if (left < right) {
        return 0L
    }
    return left - right
}
