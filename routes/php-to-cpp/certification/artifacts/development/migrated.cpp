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

std::int64_t elmos_fn_568ae835cf7acbba(std::int64_t elmos_p000_44873a91f772bd52, std::int64_t elmos_p001_432164ddb5898c60) {
    if ((elmos_p000_44873a91f772bd52 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_44873a91f772bd52, elmos_p001_432164ddb5898c60);
}
