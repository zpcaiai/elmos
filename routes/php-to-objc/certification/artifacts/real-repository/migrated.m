#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_3c97ccf710879b19(long long elmos_p000_1192fabcbdff03d0, long long elmos_p001_680e212c9be7b262) {
    if ((elmos_p000_1192fabcbdff03d0 < elmos_p001_680e212c9be7b262)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_1192fabcbdff03d0, elmos_p001_680e212c9be7b262);
}
