fn clamp(value: f64, upper: f64) -> f64 {
    if value > upper {
        return upper;
    }
    if value < (0 as f64) {
        return 0 as f64;
    }
    return value;
}
