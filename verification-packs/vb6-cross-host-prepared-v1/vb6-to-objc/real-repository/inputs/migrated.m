#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_c4c86c2555228912(long long elmos_p000_80b5cf1c7649c7e1, long long elmos_p001_6c85e2f2d34f41f0) {
    if ((elmos_p000_80b5cf1c7649c7e1 < elmos_p001_6c85e2f2d34f41f0)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_80b5cf1c7649c7e1, elmos_p001_6c85e2f2d34f41f0);
}
