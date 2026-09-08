#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_b47aa4ba556d2a5e(long long elmos_p000_2acd2dbae3ee2ee2, long long elmos_p001_47e40805ddf00d23) {
    if ((elmos_p000_2acd2dbae3ee2ee2 < elmos_p001_47e40805ddf00d23)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_2acd2dbae3ee2ee2, elmos_p001_47e40805ddf00d23);
}
