fun calculate(subtotal: Long, tax: Long): Long {
    if ((subtotal < 0L)) {
        return 0L
    }
    return Math.addExact(subtotal, tax)
}
