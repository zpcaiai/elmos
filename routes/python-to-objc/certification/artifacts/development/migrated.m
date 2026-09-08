#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_e44537fe30aaeec2(long long elmos_p000_f4265b2597827ebe, long long elmos_p001_c1bcdc3f0f7401d6) {
    if ((elmos_p000_f4265b2597827ebe < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_f4265b2597827ebe, elmos_p001_c1bcdc3f0f7401d6);
}
