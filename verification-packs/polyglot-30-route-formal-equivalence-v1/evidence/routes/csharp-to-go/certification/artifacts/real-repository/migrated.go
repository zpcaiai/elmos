package main

func elmosCheckedSub(left int64, right int64) int64 {
    difference := left - right
    if (right < 0 && difference < left) || (right > 0 && difference > left) {
        panic("ELMOS_INTEGER_OVERFLOW")
    }
    return difference
}

func difference(left int64, right int64) int64 {
    if (left < right) {
        return 0
    }
    return elmosCheckedSub(left, right)
}
