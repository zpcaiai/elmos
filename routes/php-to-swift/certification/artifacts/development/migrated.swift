func elmos_fn_6c1b191a95fbe43e(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if ((subtotal < Int64(0))) {
        return Int64(0)
    }
    return (subtotal + tax)
}
