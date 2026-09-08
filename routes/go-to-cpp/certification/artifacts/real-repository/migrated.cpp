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

std::int64_t elmos_fn_b3fa3e72c17deb10(std::int64_t elmos_p000_670f8bc5351b1284, std::int64_t elmos_p001_7f65ef1c27b7898b) {
    if ((elmos_p000_670f8bc5351b1284 < elmos_p001_7f65ef1c27b7898b)) {
        return 0;
    }
    return elmos_checked_sub(elmos_p000_670f8bc5351b1284, elmos_p001_7f65ef1c27b7898b);
}
