func elmos_fn_9478c635de40ca2b(_ left: Bool, _ right: Bool) -> Bool {
    return (left && right)
}

func elmos_fn_fb07beb31e78128c(_ subtotal: Int64, _ tax: Int64) -> Int64 {
    if ((subtotal < Int64(0))) {
        return Int64(0)
    }
    return (subtotal + tax)
}

func elmos_fn_275cfcd741bac769(_ value: Int64, _ minimum: Int64, _ maximum: Int64) -> Int64 {
    if ((value < minimum)) {
        return minimum
    }
    if ((value > maximum)) {
        return maximum
    }
    return value
}

func elmos_fn_d25a1076e5f1fbd7(_ value: Double, _ minimum: Double, _ maximum: Double) -> Double {
    if ((value < minimum)) {
        return minimum
    }
    if ((value > maximum)) {
        return maximum
    }
    return value
}

func elmos_fn_004d6bf9ce917ed8(_ left: Int64, _ right: Int64) -> Int64 {
    return (left - right)
}
