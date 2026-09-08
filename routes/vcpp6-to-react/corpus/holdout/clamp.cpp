__int64 clamp(__int64 value, __int64 upper) {
    if (value > upper) {
        return upper;
    }
    if (value < 0) {
        return 0;
    }
    return value;
}
