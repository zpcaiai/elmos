fn calculate(subtotal: i64, tax: i64) -> i64 {
    if subtotal < 0 {
        return 0;
    }
    return (subtotal).checked_add(tax).expect("ELMOS_INTEGER_OVERFLOW");
}
