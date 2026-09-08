func elmos_fn_20ffab8ae84c33b8(_ left: Bool, _ right: Bool) -> Bool {
    return (left && right)
}

func elmos_fn_0a5c7c536d88ba83(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if ((subtotal < Int64(0))) {
        return Int64(0)
    }
    return (subtotal + tax)
}

func elmos_fn_da0ad32edb107786(_ value: Int64, _ minimum: Int64, _ maximum: Int64) -> Int64 {
    if ((value < minimum)) {
        return minimum
    }
    if ((value > maximum)) {
        return maximum
    }
    return value
}

func elmos_fn_305d682d41f301b3(_ value: Double, _ minimum: Double, _ maximum: Double) -> Double {
    if ((value < minimum)) {
        return minimum
    }
    if ((value > maximum)) {
        return maximum
    }
    return value
}

func elmos_fn_b823d02cc5dd035c(_ left: Int64, _ right: Int64) -> Int64 {
    return (left - right)
}
