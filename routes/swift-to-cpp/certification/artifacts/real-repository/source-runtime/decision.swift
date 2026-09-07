func decision(_ left: Bool, _ right: Bool, _ fallback: Bool) -> Bool {
    if (left && right) || fallback { return true }
    return false
}
