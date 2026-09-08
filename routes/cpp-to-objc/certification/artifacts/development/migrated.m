#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_ad6f2ef7e718c693(long long elmos_p000_3a4a845a571a552d, long long elmos_p001_290625cff775ffd4) {
    if ((elmos_p000_3a4a845a571a552d < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_3a4a845a571a552d, elmos_p001_290625cff775ffd4);
}
