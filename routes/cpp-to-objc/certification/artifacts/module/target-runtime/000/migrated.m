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

BOOL both(BOOL left, BOOL right) {
    return (left && right);
}

long long calculate(long long subtotal, long long tax) {
    if ((subtotal < 0)) {
        return 0;
    }
    return ElmosCheckedAdd(subtotal, tax);
}

long long clamp(long long value, long long minimum, long long maximum) {
    if ((value < minimum)) {
        return minimum;
    }
    if ((value > maximum)) {
        return maximum;
    }
    return value;
}

double clampNumber(double value, double minimum, double maximum) {
    if ((value < minimum)) {
        return minimum;
    }
    if ((value > maximum)) {
        return maximum;
    }
    return value;
}

long long difference(long long left, long long right) {
    return ElmosCheckedSub(left, right);
}
