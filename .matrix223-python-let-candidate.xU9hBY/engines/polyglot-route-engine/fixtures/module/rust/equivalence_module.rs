fn calculate(subtotal: i64, tax: i64) -> i64 {
    if subtotal < 0 { return 0; }
    subtotal + tax
}

fn clamp(value: i64, minimum: i64, maximum: i64) -> i64 {
    if value < minimum { return minimum; }
    if value > maximum { return maximum; }
    value
}

fn difference(left: i64, right: i64) -> i64 { left - right }

fn clampNumber(value: f64, minimum: f64, maximum: f64) -> f64 {
    if value < minimum { return minimum; }
    if value > maximum { return maximum; }
    value
}

fn both(left: bool, right: bool) -> bool { left && right }
