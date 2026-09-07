#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include "migrated.cpp"

[[maybe_unused]] static std::uint64_t elmos_harness_fp64_bits(double value) {
    std::uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

[[maybe_unused]] static bool elmos_harness_same_fp64(double left, double right) {
    return (std::isnan(left) && std::isnan(right)) ||
           elmos_harness_fp64_bits(left) == elmos_harness_fp64_bits(right);
}

[[maybe_unused]] static std::string elmos_harness_fp64(double value) {
    std::ostringstream stream;
    stream << std::hex << std::setfill('0') << std::setw(16)
           << elmos_harness_fp64_bits(value);
    return stream.str();
}

[[maybe_unused]] static std::string elmos_harness_hex_utf8(const std::string &value) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string encoded;
    encoded.reserve(value.size() * 2);
    for (const unsigned char byte : value) {
        encoded.push_back(digits[byte >> 4]);
        encoded.push_back(digits[byte & 0x0f]);
    }
    return encoded;
}

int main() {
    const auto actual_0 = clamp(-10, 0, 100);
    const auto expected_0 = 0;
    if (actual_0 != expected_0) return 1;
    std::cout << "ELMOS_OBSERVATION\t0\ti64-dec\t" << std::to_string(actual_0) << "\n";
    const auto actual_1 = clamp(55, 0, 100);
    const auto expected_1 = 55;
    if (actual_1 != expected_1) return 2;
    std::cout << "ELMOS_OBSERVATION\t1\ti64-dec\t" << std::to_string(actual_1) << "\n";
    const auto actual_2 = clamp(101, 0, 100);
    const auto expected_2 = 100;
    if (actual_2 != expected_2) return 3;
    std::cout << "ELMOS_OBSERVATION\t2\ti64-dec\t" << std::to_string(actual_2) << "\n";
    const auto actual_3 = clamp(0, 0, 100);
    const auto expected_3 = 0;
    if (actual_3 != expected_3) return 4;
    std::cout << "ELMOS_OBSERVATION\t3\ti64-dec\t" << std::to_string(actual_3) << "\n";
    const auto actual_4 = clamp(100, 0, 100);
    const auto expected_4 = 100;
    if (actual_4 != expected_4) return 5;
    std::cout << "ELMOS_OBSERVATION\t4\ti64-dec\t" << std::to_string(actual_4) << "\n";
    return 0;
}
