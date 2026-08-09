fn difference(left: f64, right: f64) -> f64 {
    if left < right {
        return 0 as f64;
    }
    return left - right;
}
