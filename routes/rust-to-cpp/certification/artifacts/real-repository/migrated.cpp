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

std::int64_t elmos_fn_8582f6215b22eff7(std::int64_t elmos_p000_0b9db0366842cc65, std::int64_t elmos_p001_b9876ac8573a1cb8) {
    if ((elmos_p000_0b9db0366842cc65 < elmos_p001_b9876ac8573a1cb8)) {
        return 0;
    }
    return elmos_checked_sub(elmos_p000_0b9db0366842cc65, elmos_p001_b9876ac8573a1cb8);
}
