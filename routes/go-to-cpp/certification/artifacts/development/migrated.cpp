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

std::int64_t elmos_fn_d25ffefcecb93100(std::int64_t elmos_p000_354db69a47264478, std::int64_t elmos_p001_d4ee097f6f31ad23) {
    if ((elmos_p000_354db69a47264478 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_354db69a47264478, elmos_p001_d4ee097f6f31ad23);
}
