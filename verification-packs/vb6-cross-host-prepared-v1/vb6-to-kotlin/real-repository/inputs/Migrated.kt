fun difference(left: Long, right: Long): Long {
    if ((left < right)) {
        return 0L
    }
    return Math.subtractExact(left, right)
}
