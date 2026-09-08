func clamp(_ value: Int64, _ upper: Int64) -> Int64 {
    if value > upper {
        return upper
    }
    if value < 0 {
        return 0
    }
    return value
}
