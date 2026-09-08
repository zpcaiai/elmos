#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_c21b31dfaff812b1(long long elmos_p000_a325e918ec218ba8, long long elmos_p001_6aa033bc748cafbd) {
    if ((elmos_p000_a325e918ec218ba8 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_a325e918ec218ba8, elmos_p001_6aa033bc748cafbd);
}
