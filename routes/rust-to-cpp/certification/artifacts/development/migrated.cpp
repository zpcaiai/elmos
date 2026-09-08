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

std::int64_t elmos_fn_589080a7e0da08e6(std::int64_t elmos_p000_13eb3567a0239fa8, std::int64_t elmos_p001_c6af31ce38951881) {
    if ((elmos_p000_13eb3567a0239fa8 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_13eb3567a0239fa8, elmos_p001_c6af31ce38951881);
}
