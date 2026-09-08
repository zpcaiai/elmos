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

std::int64_t elmos_fn_680dd7ae0df58542(std::int64_t elmos_p000_3db3b992d90034ec, std::int64_t elmos_p001_500987ac1f229449) {
    if ((elmos_p000_3db3b992d90034ec < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_3db3b992d90034ec, elmos_p001_500987ac1f229449);
}
