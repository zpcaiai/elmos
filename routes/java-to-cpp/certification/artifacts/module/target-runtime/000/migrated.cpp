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

bool elmos_fn_7593e4aca0357f18(bool elmos_p000_53ee0c0dc7d37f34, bool elmos_p001_1ac4b85273361501) {
    return (elmos_p000_53ee0c0dc7d37f34 && elmos_p001_1ac4b85273361501);
}

std::int64_t elmos_fn_8efef4422e0cb671(std::int64_t elmos_p000_d50a8d7085768191, std::int64_t elmos_p001_fd646bef911b2fd2) {
    if ((elmos_p000_d50a8d7085768191 < 0)) {
        return 0;
    }
    return elmos_checked_add(elmos_p000_d50a8d7085768191, elmos_p001_fd646bef911b2fd2);
}

std::int64_t elmos_fn_c975e17d9e6a9021(std::int64_t elmos_p000_55aadea8c11d7754, std::int64_t elmos_p001_b47fe8b0f91ddb10, std::int64_t elmos_p002_8253fbf66bf74aad) {
    if ((elmos_p000_55aadea8c11d7754 < elmos_p001_b47fe8b0f91ddb10)) {
        return elmos_p001_b47fe8b0f91ddb10;
    }
    if ((elmos_p000_55aadea8c11d7754 > elmos_p002_8253fbf66bf74aad)) {
        return elmos_p002_8253fbf66bf74aad;
    }
    return elmos_p000_55aadea8c11d7754;
}

double elmos_fn_c475b1fac1b34de4(double elmos_p000_d4f4478b81888062, double elmos_p001_872ad24aafadd054, double elmos_p002_000e6b8ff40cfd8c) {
    if ((elmos_p000_d4f4478b81888062 < elmos_p001_872ad24aafadd054)) {
        return elmos_p001_872ad24aafadd054;
    }
    if ((elmos_p000_d4f4478b81888062 > elmos_p002_000e6b8ff40cfd8c)) {
        return elmos_p002_000e6b8ff40cfd8c;
    }
    return elmos_p000_d4f4478b81888062;
}

std::int64_t elmos_fn_a83e40c09f4bf5d9(std::int64_t elmos_p000_2f0cf04dda1f8b59, std::int64_t elmos_p001_060cc2931bfe40a8) {
    return elmos_checked_sub(elmos_p000_2f0cf04dda1f8b59, elmos_p001_060cc2931bfe40a8);
}
