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
        double actual_0 = elmos_fn_1543309208db8531(20.0, 10.0);
        double expected_0 = 10.0;
        if (!ElmosHarnessSameFP64(actual_0, expected_0)) return 1;
        printf("ELMOS_OBSERVATION\t0\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_0) UTF8String]);
        double actual_1 = elmos_fn_1543309208db8531(-2.0, 10.0);
        double expected_1 = 0.0;
        if (!ElmosHarnessSameFP64(actual_1, expected_1)) return 2;
        printf("ELMOS_OBSERVATION\t1\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_1) UTF8String]);
        double actual_2 = elmos_fn_1543309208db8531(7.0, 10.0);
        double expected_2 = 7.0;
        if (!ElmosHarnessSameFP64(actual_2, expected_2)) return 3;
        printf("ELMOS_OBSERVATION\t2\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_2) UTF8String]);
    }
    return 0;
}
