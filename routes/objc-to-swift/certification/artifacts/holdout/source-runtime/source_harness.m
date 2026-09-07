#import <Foundation/Foundation.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#import "echo_number.m"

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
        double actual_0 = echoNumber(-0.0);
        double expected_0 = -0.0;
        if (!ElmosHarnessSameFP64(actual_0, expected_0)) return 1;
        printf("ELMOS_OBSERVATION\t0\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_0) UTF8String]);
        double actual_1 = echoNumber(0.0);
        double expected_1 = 0.0;
        if (!ElmosHarnessSameFP64(actual_1, expected_1)) return 2;
        printf("ELMOS_OBSERVATION\t1\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_1) UTF8String]);
        double actual_2 = echoNumber(1.7976931348623157e+308);
        double expected_2 = 1.7976931348623157e+308;
        if (!ElmosHarnessSameFP64(actual_2, expected_2)) return 3;
        printf("ELMOS_OBSERVATION\t2\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_2) UTF8String]);
        double actual_3 = echoNumber(-1.7976931348623157e+308);
        double expected_3 = -1.7976931348623157e+308;
        if (!ElmosHarnessSameFP64(actual_3, expected_3)) return 4;
        printf("ELMOS_OBSERVATION\t3\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_3) UTF8String]);
        double actual_4 = echoNumber(2.2250738585072014e-308);
        double expected_4 = 2.2250738585072014e-308;
        if (!ElmosHarnessSameFP64(actual_4, expected_4)) return 5;
        printf("ELMOS_OBSERVATION\t4\tfp64-hex\t%s\n", [ElmosHarnessFP64(actual_4) UTF8String]);
    }
    return 0;
}
