bool decision(bool left, bool right, bool fallback) {
    if ((left && right) || fallback) { return true; }
    return false;
}
