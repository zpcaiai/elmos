func calculate(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if subtotal < 0 {
        return 0
    }
    return subtotal + tax
}

func clamp(_ value: Int64, _ minimum: Int64, _ maximum: Int64) -> Int64 {
    if value < minimum {
        return minimum
    }
    if value > maximum {
        return maximum
    }
    return value
}

func difference(_ left: Int64, _ right: Int64) -> Int64 {
    return left - right
}

func clampNumber(_ value: Double, _ minimum: Double, _ maximum: Double) -> Double {
    if value < minimum {
        return minimum
    }
    if value > maximum {
        return maximum
    }
    return value
}

func both(_ left: Bool, _ right: Bool) -> Bool {
    return left && right
}
