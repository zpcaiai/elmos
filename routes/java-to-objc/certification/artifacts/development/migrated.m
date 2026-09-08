#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_5db0a60115807ea2(long long elmos_p000_c0a16f5fc14d885b, long long elmos_p001_e6d27b56dd3848c7) {
    if ((elmos_p000_c0a16f5fc14d885b < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_c0a16f5fc14d885b, elmos_p001_e6d27b56dd3848c7);
}
