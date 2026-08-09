#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long calculate(long long subtotal, long long tax) {
    if ((subtotal < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(subtotal, tax);
}
