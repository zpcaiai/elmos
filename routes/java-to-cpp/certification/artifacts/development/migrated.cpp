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

std::int64_t elmos_fn_59a8dd52c6a88ee6(std::int64_t elmos_p000_43539b782ea1e621, std::int64_t elmos_p001_5f08b19948744f29) {
    if ((elmos_p000_43539b782ea1e621 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_43539b782ea1e621, elmos_p001_5f08b19948744f29);
}
