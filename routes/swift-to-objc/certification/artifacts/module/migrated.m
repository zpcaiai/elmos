#import <Foundation/Foundation.h>

static long long ElmosCheckedAdd(long long left, long long right) {
    long long result = 0;
    if (__builtin_add_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

static long long ElmosCheckedSub(long long left, long long right) {
    long long result = 0;
    if (__builtin_sub_overflow(left, right, &result)) {
        [NSException raise:@"ElmosArithmeticError" format:@"ELMOS_INTEGER_OVERFLOW"];
    }
    return result;
}

BOOL elmos_fn_d78d3e483b14bbac(BOOL elmos_p000_3d991f85167873ba, BOOL elmos_p001_7ef727c2d74e4b49) {
    return (elmos_p000_3d991f85167873ba && elmos_p001_7ef727c2d74e4b49);
}

long long elmos_fn_71f8d4ee14897ddf(long long elmos_p000_06c193718d10c87b, long long elmos_p001_282cc0b3de08cb13) {
    if ((elmos_p000_06c193718d10c87b < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_06c193718d10c87b, elmos_p001_282cc0b3de08cb13);
}

long long elmos_fn_6236e9dee9c18de3(long long elmos_p000_a23ca96616ad898a, long long elmos_p001_c5ec28419a3163ae, long long elmos_p002_8c26fc00173048ac) {
    if ((elmos_p000_a23ca96616ad898a < elmos_p001_c5ec28419a3163ae)) {
        return elmos_p001_c5ec28419a3163ae;
    }
    if ((elmos_p000_a23ca96616ad898a > elmos_p002_8c26fc00173048ac)) {
        return elmos_p002_8c26fc00173048ac;
    }
    return elmos_p000_a23ca96616ad898a;
}

double elmos_fn_381c27419f9e5857(double elmos_p000_989480a609bbd665, double elmos_p001_ec646907bd2cc21f, double elmos_p002_c592faece1a17f84) {
    if ((elmos_p000_989480a609bbd665 < elmos_p001_ec646907bd2cc21f)) {
        return elmos_p001_ec646907bd2cc21f;
    }
    if ((elmos_p000_989480a609bbd665 > elmos_p002_c592faece1a17f84)) {
        return elmos_p002_c592faece1a17f84;
    }
    return elmos_p000_989480a609bbd665;
}

long long elmos_fn_17c1997e72cd67db(long long elmos_p000_60983cd1b91dc070, long long elmos_p001_8125f67a3a77b4ea) {
    return ElmosCheckedSub(elmos_p000_60983cd1b91dc070, elmos_p001_8125f67a3a77b4ea);
}
