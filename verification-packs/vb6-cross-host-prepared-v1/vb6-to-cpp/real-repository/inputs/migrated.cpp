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

std::int64_t elmos_fn_d1d4a2e17cb922f3(std::int64_t elmos_p000_e318e62e94a12ce0, std::int64_t elmos_p001_358c391cabbe7242) {
    if ((elmos_p000_e318e62e94a12ce0 < elmos_p001_358c391cabbe7242)) {
        return 0;
    }
    return elmos_checked_sub(elmos_p000_e318e62e94a12ce0, elmos_p001_358c391cabbe7242);
}
