#import <Foundation/Foundation.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#import "migrated.m"

static __attribute__((unused)) uint64_t ElmosHarnessFP64Bits(double value) {
    uint64_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static __attribute__((unused)) BOOL ElmosHarnessSameFP64(double left, double right) {
    return (isnan(left) && isnan(right)) ||
           ElmosHarnessFP64Bits(left) == ElmosHarnessFP64Bits(right);
}

static __attribute__((unused)) NSString *ElmosHarnessFP64(double value) {
    return [NSString stringWithFormat:@"%016llx", (unsigned long long)ElmosHarnessFP64Bits(value)];
}

static __attribute__((unused)) NSString *ElmosHarnessHexUTF8(NSString *value) {
    NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];
    const unsigned char *bytes = data.bytes;
    NSMutableString *result = [NSMutableString stringWithCapacity:data.length * 2];
    for (NSUInteger index = 0; index < data.length; index++) {
        [result appendFormat:@"%02x", (unsigned int)bytes[index]];
    }
    return result;
}

int main() {
    @autoreleasepool {
        long long actual_0 = calculate(100, 20);
        long long expected_0 = 120;
        if (actual_0 != expected_0) return 1;
        printf("ELMOS_OBSERVATION\t0\ti64-dec\t%lld\n", actual_0);
        long long actual_1 = calculate(-1, 20);
        long long expected_1 = 0;
        if (actual_1 != expected_1) return 2;
        printf("ELMOS_OBSERVATION\t1\ti64-dec\t%lld\n", actual_1);
        long long actual_2 = calculate(0, 0);
        long long expected_2 = 0;
        if (actual_2 != expected_2) return 3;
        printf("ELMOS_OBSERVATION\t2\ti64-dec\t%lld\n", actual_2);
        long long actual_3 = calculate(9223372036854775700LL, 7);
        long long expected_3 = 9223372036854775707LL;
        if (actual_3 != expected_3) return 4;
        printf("ELMOS_OBSERVATION\t3\ti64-dec\t%lld\n", actual_3);
    }
    return 0;
}
