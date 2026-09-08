__int64 calculate(__int64 subtotal, __int64 tax) {
    if (subtotal < 0) {
        return 0;
    }
    return subtotal + tax;
}
