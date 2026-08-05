package representative

func difference(left int64, right int64) int64 {
    if left < right {
        return 0
    }
    return left - right
}
