func elmos_fn_87c620e7ad318001(_ value: Double, _ upper: Double) -> Double {
    if ((value > upper)) {
        return upper
    }
    if ((value < Double(Int64(0)))) {
        return Double(Int64(0))
    }
    return value
}
