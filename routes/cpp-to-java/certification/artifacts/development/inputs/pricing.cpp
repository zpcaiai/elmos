#include <cstdint>
std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {
    if (subtotal < 0) { return 0; }
    return subtotal + tax;
}
