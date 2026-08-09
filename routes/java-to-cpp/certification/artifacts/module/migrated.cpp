#include <cstdint>
#include <stdexcept>
#include <string>

std::int64_t elmos_checked_add(std::int64_t left, std::int64_t right) {
    std::int64_t result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        throw std::overflow_error("ELMOS_INTEGER_OVERFLOW");
    }
    return result;
}

std::int64_t elmos_checked_sub(std::int64_t left, std::int64_t right) {
    std::int64_t result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        throw std::overflow_error("ELMOS_INTEGER_OVERFLOW");
    }
    return result;
}

bool both(bool left, bool right) {
    return (left && right);
}

std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {
    if ((subtotal < 0)) {
        return 0;
    }
    return elmos_checked_add(subtotal, tax);
}

std::int64_t clamp(std::int64_t value, std::int64_t minimum, std::int64_t maximum) {
    if ((value < minimum)) {
        return minimum;
    }
    if ((value > maximum)) {
        return maximum;
    }
    return value;
}

double clampNumber(double value, double minimum, double maximum) {
    if ((value < minimum)) {
        return minimum;
    }
    if ((value > maximum)) {
        return maximum;
    }
    return value;
}

std::int64_t difference(std::int64_t left, std::int64_t right) {
    return elmos_checked_sub(left, right);
}
