fn calculate(subtotal: f64, tax: f64) -> f64 {
    if subtotal < (0 as f64) {
        return 0 as f64;
    }
    return subtotal + tax;
}
