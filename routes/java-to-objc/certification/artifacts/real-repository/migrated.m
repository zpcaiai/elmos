#import <Foundation/Foundation.h>

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

long long elmos_fn_139b64cf1d7740aa(long long elmos_p000_7b2199f07fb58fde, long long elmos_p001_702723452f5c9842) {
    if ((elmos_p000_7b2199f07fb58fde < elmos_p001_702723452f5c9842)) {
        return 0;
    }
    return ElmosCheckedSub(elmos_p000_7b2199f07fb58fde, elmos_p001_702723452f5c9842);
}
