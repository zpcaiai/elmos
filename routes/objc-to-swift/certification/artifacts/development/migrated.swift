func elmos_fn_76f71d9e8b8f63b6(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if ((subtotal < Int64(0))) {
        return Int64(0)
    }
    return (subtotal + tax)
}
