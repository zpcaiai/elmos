func calculate(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if ((subtotal < Int64(0))) {
        return Int64(0)
    }
    return (subtotal + tax)
}
