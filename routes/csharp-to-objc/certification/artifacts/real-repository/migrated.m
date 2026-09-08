#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_b7bfbf5a3cf754df(long long elmos_p000_b4493bf2f033afb5, long long elmos_p001_7e1ac10b300ea040) {
    if ((elmos_p000_b4493bf2f033afb5 < elmos_p001_7e1ac10b300ea040)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_b4493bf2f033afb5, elmos_p001_7e1ac10b300ea040);
}
