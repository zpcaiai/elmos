#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_bf8e0a79eb066257(long long elmos_p000_f553e0c354ebfb13, long long elmos_p001_187c8627c67601c1) {
    if ((elmos_p000_f553e0c354ebfb13 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_f553e0c354ebfb13, elmos_p001_187c8627c67601c1);
}
