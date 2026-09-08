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

static std::int64_t elmos_checked_sub(std::int64_t left, std::int64_t right) {
    std::int64_t result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        throw std::overflow_error("ELMOS_INTEGER_OVERFLOW");
    }
    return result;
}

bool elmos_fn_e3511cdd5c2343d8(bool elmos_p000_fa4d830187524564, bool elmos_p001_782aad879363aad0) {
    return (elmos_p000_fa4d830187524564 && elmos_p001_782aad879363aad0);
}

std::int64_t elmos_fn_29e2ecaf1ed07ede(std::int64_t elmos_p000_af2eb43755dcc32c, std::int64_t elmos_p001_f84114e80678849d) {
    if ((elmos_p000_af2eb43755dcc32c < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_af2eb43755dcc32c, elmos_p001_f84114e80678849d);
}

std::int64_t elmos_fn_0f6e2f6ed475971e(std::int64_t elmos_p000_188e80481209069a, std::int64_t elmos_p001_cf252b089817d9b9, std::int64_t elmos_p002_4373500dc845d1e4) {
    if ((elmos_p000_188e80481209069a < elmos_p001_cf252b089817d9b9)) {
        return elmos_p001_cf252b089817d9b9;
    }
    if ((elmos_p000_188e80481209069a > elmos_p002_4373500dc845d1e4)) {
        return elmos_p002_4373500dc845d1e4;
    }
    return elmos_p000_188e80481209069a;
}

double elmos_fn_39e1fbc64d68e5c6(double elmos_p000_8cdf1338f7790002, double elmos_p001_25aabf64a746e69e, double elmos_p002_3f06c7ec1dc3c8d2) {
    if ((elmos_p000_8cdf1338f7790002 < elmos_p001_25aabf64a746e69e)) {
        return elmos_p001_25aabf64a746e69e;
    }
    if ((elmos_p000_8cdf1338f7790002 > elmos_p002_3f06c7ec1dc3c8d2)) {
        return elmos_p002_3f06c7ec1dc3c8d2;
    }
    return elmos_p000_8cdf1338f7790002;
}

std::int64_t elmos_fn_13a976b40385f58e(std::int64_t elmos_p000_f246d2a9f66642af, std::int64_t elmos_p001_e2cdf086fe4d1abf) {
    return elmos_checked_sub(elmos_p000_f246d2a9f66642af, elmos_p001_e2cdf086fe4d1abf);
}
