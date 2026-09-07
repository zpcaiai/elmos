#import <Foundation/Foundation.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#import "equivalence_module.m"

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
        BOOL actual_0 = both(YES, YES);
        BOOL expected_0 = YES;
        if (actual_0 != expected_0) return 1;
        printf("ELMOS_OBSERVATION\t0\tbool\t%s\n", actual_0 ? "true" : "false");
        BOOL actual_1 = both(YES, NO);
        BOOL expected_1 = NO;
        if (actual_1 != expected_1) return 2;
        printf("ELMOS_OBSERVATION\t1\tbool\t%s\n", actual_1 ? "true" : "false");
        BOOL actual_2 = both(NO, YES);
        BOOL expected_2 = NO;
        if (actual_2 != expected_2) return 3;
        printf("ELMOS_OBSERVATION\t2\tbool\t%s\n", actual_2 ? "true" : "false");
        BOOL actual_3 = both(NO, NO);
        BOOL expected_3 = NO;
        if (actual_3 != expected_3) return 4;
        printf("ELMOS_OBSERVATION\t3\tbool\t%s\n", actual_3 ? "true" : "false");
    }
    return 0;
}
