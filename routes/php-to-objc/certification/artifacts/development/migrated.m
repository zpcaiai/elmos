#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_577662b0637675cd(long long elmos_p000_a933ea55b55fdc03, long long elmos_p001_6ed2121e3db036b6) {
    if ((elmos_p000_a933ea55b55fdc03 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_a933ea55b55fdc03, elmos_p001_6ed2121e3db036b6);
}
