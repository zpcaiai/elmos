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

std::int64_t elmos_fn_3fe4b5b9f0e33828(std::int64_t elmos_p000_c9ef3d5313fbf018, std::int64_t elmos_p001_d7a2284365b8d6f3) {
    if ((elmos_p000_c9ef3d5313fbf018 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_c9ef3d5313fbf018, elmos_p001_d7a2284365b8d6f3);
}
