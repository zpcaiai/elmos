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

std::int64_t elmos_fn_63308dfca677c22c(std::int64_t elmos_p000_f9f2401bebd5e0c5, std::int64_t elmos_p001_f60d1cbf69ff4ee8) {
    if ((elmos_p000_f9f2401bebd5e0c5 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_f9f2401bebd5e0c5, elmos_p001_f60d1cbf69ff4ee8);
}
