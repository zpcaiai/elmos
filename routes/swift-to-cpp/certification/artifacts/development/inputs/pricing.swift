func calculate(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if subtotal < 0 { return 0 }
    return subtotal + tax
}
