#include <cstdint>

std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {
    if (subtotal < 0) {
        return 0;
    }
    return subtotal + tax;
}

std::int64_t clamp(std::int64_t value, std::int64_t minimum, std::int64_t maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}

std::int64_t difference(std::int64_t left, std::int64_t right) {
    return left - right;
}

double clampNumber(double value, double minimum, double maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}

bool both(bool left, bool right) {
    return left && right;
}
