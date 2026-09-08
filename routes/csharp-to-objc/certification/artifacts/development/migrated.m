#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_80c9956fd11d1e58(long long elmos_p000_9b7fad80a675ab5c, long long elmos_p001_97c7f179f09f7b10) {
    if ((elmos_p000_9b7fad80a675ab5c < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_9b7fad80a675ab5c, elmos_p001_97c7f179f09f7b10);
}
