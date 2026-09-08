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

BOOL elmos_fn_9ff8f7f981bbef0d(BOOL elmos_p000_25cec0c653213203, BOOL elmos_p001_200a1d5ff3f26ac7) {
    return (elmos_p000_25cec0c653213203 && elmos_p001_200a1d5ff3f26ac7);
}

long long elmos_fn_4cfdd4603f680c60(long long elmos_p000_41e20d437f1446a0, long long elmos_p001_0f63d3bee312f451) {
    if ((elmos_p000_41e20d437f1446a0 < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(elmos_p000_41e20d437f1446a0, elmos_p001_0f63d3bee312f451);
}

long long elmos_fn_d061a95391d14e41(long long elmos_p000_8a176273d386aebb, long long elmos_p001_34201f8b39fa1432, long long elmos_p002_df05ed0c561c3fac) {
    if ((elmos_p000_8a176273d386aebb < elmos_p001_34201f8b39fa1432)) {
        return elmos_p001_34201f8b39fa1432;
    }
    if ((elmos_p000_8a176273d386aebb > elmos_p002_df05ed0c561c3fac)) {
        return elmos_p002_df05ed0c561c3fac;
    }
    return elmos_p000_8a176273d386aebb;
}

double elmos_fn_3f569ce090deee55(double elmos_p000_cf0bff9a59a7362e, double elmos_p001_49967dd6f06593e6, double elmos_p002_7b03f480c26fe3dd) {
    if ((elmos_p000_cf0bff9a59a7362e < elmos_p001_49967dd6f06593e6)) {
        return elmos_p001_49967dd6f06593e6;
    }
    if ((elmos_p000_cf0bff9a59a7362e > elmos_p002_7b03f480c26fe3dd)) {
        return elmos_p002_7b03f480c26fe3dd;
    }
    return elmos_p000_cf0bff9a59a7362e;
}

long long elmos_fn_b3b1207c175e132c(long long elmos_p000_b11a6d9420ae7e6f, long long elmos_p001_be2acbff6423f927) {
    return ElmosCheckedSub(elmos_p000_b11a6d9420ae7e6f, elmos_p001_be2acbff6423f927);
}
