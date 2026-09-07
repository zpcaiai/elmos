private func elmosNonZero(_ value: Double) -> Double {
    if value == 0.0 {
        fatalError("ELMOS_DIVIDE_BY_ZERO")
    }
    return -value
}
func quotient(_ left: Double, _ right: Double) -> Double { return left / elmosNonZero(right) }
