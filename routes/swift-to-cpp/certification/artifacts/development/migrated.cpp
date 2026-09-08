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

std::int64_t elmos_fn_cd34b3e5a55edbfa(std::int64_t elmos_p000_5e79a0177f062b7b, std::int64_t elmos_p001_2e4719cf7d0e3db1) {
    if ((elmos_p000_5e79a0177f062b7b < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_5e79a0177f062b7b, elmos_p001_2e4719cf7d0e3db1);
}
