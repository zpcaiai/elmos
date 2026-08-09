fn difference(left: i64, right: i64) -> i64 {
    if left < right {
        return 0;
    }
    return (left).checked_sub(right).expect("ELMOS_INTEGER_OVERFLOW");
}
