func clamp(_ value: Int, _ upper: Int) -> Int {
    if value > upper {
        return upper
    }
    if value < 0 {
        return 0
    }
    return value
}
