package main

func elmosCheckedAdd(left int64, right int64) int64 {
    sum := left + right
    if (right > 0 && sum < left) || (right < 0 && sum > left) {
        panic("ELMOS_INTEGER_OVERFLOW")
    }
    return sum
}

func calculate(subtotal int64, tax int64) int64 {
    if (subtotal < 0) {
        return 0
    }
    return elmosCheckedAdd(subtotal, tax)
}
