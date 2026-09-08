#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_76cebca0ef07f83c(long long elmos_p000_9b409638227a63e8, long long elmos_p001_33dbb7ecf85fde41) {
    if ((elmos_p000_9b409638227a63e8 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_9b409638227a63e8, elmos_p001_33dbb7ecf85fde41);
}
