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

std::int64_t elmos_fn_61024caffc4d8d9f(std::int64_t elmos_p000_bd6c2acbc0a5a850, std::int64_t elmos_p001_52bbdf64f20274f1) {
    if ((elmos_p000_bd6c2acbc0a5a850 < elmos_p001_52bbdf64f20274f1)) {
        return 0;
    }
    return elmos_checked_sub(elmos_p000_bd6c2acbc0a5a850, elmos_p001_52bbdf64f20274f1);
}
