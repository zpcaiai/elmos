#include <cstdint>

std::int64_t difference(std::int64_t left, std::int64_t right) {
    if (left < right) {
        return 0;
    }
    return left - right;
}
