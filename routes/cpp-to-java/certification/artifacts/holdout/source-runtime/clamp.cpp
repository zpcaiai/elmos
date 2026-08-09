#include <cstdint>

std::int64_t clamp(std::int64_t value, std::int64_t upper) {
    if (value > upper) {
        return upper;
    }
    if (value < 0) {
        return 0;
    }
    return value;
}
