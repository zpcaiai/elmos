func elmos_fn_6dd10d65d313575e(_ value: Int64, _ upper: Int64) -> Int64 {
    if ((value > upper)) {
        return upper
    }
    if ((value < Int64(0))) {
        return Int64(0)
    }
    return value
}
