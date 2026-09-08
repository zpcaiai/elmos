func elmos_fn_ec83203006ef6bc0(_ subtotal: Double, _ tax: Double) -> Double {
    if ((subtotal < Double(Int64(0)))) {
        return Double(Int64(0))
    }
    return (subtotal + tax)
}
