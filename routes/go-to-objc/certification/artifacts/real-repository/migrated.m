#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_c558e587446ddf05(long long elmos_p000_c83352bd7864904f, long long elmos_p001_65c79ec3a98913c0) {
    if ((elmos_p000_c83352bd7864904f < elmos_p001_65c79ec3a98913c0)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_c83352bd7864904f, elmos_p001_65c79ec3a98913c0);
}
