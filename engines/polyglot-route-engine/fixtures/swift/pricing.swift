func calculate(_ subtotal: Int, _ tax: Int) -> Int {
    if subtotal < 0 {
        return 0
    }
    return subtotal + tax
}
