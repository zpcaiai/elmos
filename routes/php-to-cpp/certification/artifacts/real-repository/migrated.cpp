#include <cstdint>
#include <stdexcept>
#include <string>

static std::int64_t elmos_checked_sub(std::int64_t left, std::int64_t right) {
    std::int64_t result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        throw std::overflow_error("ELMOS_INTEGER_OVERFLOW");
    }
    return result;
}

std::int64_t elmos_fn_015d72a4076eea0b(std::int64_t elmos_p000_b2212c9283ba344b, std::int64_t elmos_p001_051183350bfadfdb) {
    if ((elmos_p000_b2212c9283ba344b < elmos_p001_051183350bfadfdb)) {
        return 0;
    }
    return elmos_checked_sub(elmos_p000_b2212c9283ba344b, elmos_p001_051183350bfadfdb);
}
