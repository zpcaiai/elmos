fn clamp(value: i64, upper: i64) -> i64 {
    if value > upper {
        return upper;
    }
    if value < 0 {
        return 0;
    }
    return value;
}
