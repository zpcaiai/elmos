#include <cstdint>
#include <stdexcept>
#include <string>

static std::int64_t elmos_checked_add(std::int64_t left, std::int64_t right) {
    std::int64_t result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        throw std::overflow_error("ELMOS_INTEGER_OVERFLOW");
    }
    return result;
}

std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {
    if ((subtotal < 0)) {
        return 0;
    }
    return elmos_checked_add(subtotal, tax);
}
