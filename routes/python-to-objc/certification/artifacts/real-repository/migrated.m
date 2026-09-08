#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_bb32c95002a7da64(long long elmos_p000_62b2a31d7768ca5e, long long elmos_p001_19e570a37b151768) {
    if ((elmos_p000_62b2a31d7768ca5e < elmos_p001_19e570a37b151768)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_62b2a31d7768ca5e, elmos_p001_19e570a37b151768);
}
