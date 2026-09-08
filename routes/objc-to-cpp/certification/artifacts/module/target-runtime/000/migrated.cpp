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

bool elmos_fn_eb8e34e30cd5818b(bool elmos_p000_8ca8f8b402a1594a, bool elmos_p001_34c6958aedb7ddb0) {
    return (elmos_p000_8ca8f8b402a1594a && elmos_p001_34c6958aedb7ddb0);
}

std::int64_t elmos_fn_55c2e805e5c2ab6c(std::int64_t elmos_p000_23d71baa40f1f19e, std::int64_t elmos_p001_1d61ce18b2e5d776) {
    if ((elmos_p000_23d71baa40f1f19e < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_23d71baa40f1f19e, elmos_p001_1d61ce18b2e5d776);
}

std::int64_t elmos_fn_72722dcfbfd84de7(std::int64_t elmos_p000_b5fa5582e64a744a, std::int64_t elmos_p001_a8f5525f97894159, std::int64_t elmos_p002_0f28eef787b238e5) {
    if ((elmos_p000_b5fa5582e64a744a < elmos_p001_a8f5525f97894159)) {
        return elmos_p001_a8f5525f97894159;
    }
    if ((elmos_p000_b5fa5582e64a744a > elmos_p002_0f28eef787b238e5)) {
        return elmos_p002_0f28eef787b238e5;
    }
    return elmos_p000_b5fa5582e64a744a;
}

double elmos_fn_a2176ee686a67480(double elmos_p000_657cb41ed23c3e68, double elmos_p001_aa2f14bf2b6b74ed, double elmos_p002_477336b37fb18cef) {
    if ((elmos_p000_657cb41ed23c3e68 < elmos_p001_aa2f14bf2b6b74ed)) {
        return elmos_p001_aa2f14bf2b6b74ed;
    }
    if ((elmos_p000_657cb41ed23c3e68 > elmos_p002_477336b37fb18cef)) {
        return elmos_p002_477336b37fb18cef;
    }
    return elmos_p000_657cb41ed23c3e68;
}

std::int64_t elmos_fn_81806116737ea305(std::int64_t elmos_p000_f6fb6ff8fbfde4cf, std::int64_t elmos_p001_4df3968c5f23592d) {
    return elmos_checked_sub(elmos_p000_f6fb6ff8fbfde4cf, elmos_p001_4df3968c5f23592d);
}
