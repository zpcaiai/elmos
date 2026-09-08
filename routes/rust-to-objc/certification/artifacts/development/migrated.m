#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_87633658da97580b(long long elmos_p000_d75dae5b127288e1, long long elmos_p001_0bcf27fcae967afe) {
    if ((elmos_p000_d75dae5b127288e1 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_d75dae5b127288e1, elmos_p001_0bcf27fcae967afe);
}
