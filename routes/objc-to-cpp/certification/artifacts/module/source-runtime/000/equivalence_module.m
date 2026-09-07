#import <Foundation/Foundation.h>

long long calculate(long long subtotal, long long tax) {
    if (subtotal < 0LL) {
        return 0LL;
    }
    return subtotal + tax;
}

long long clamp(long long value, long long minimum, long long maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}

long long difference(long long left, long long right) {
    return left - right;
}

double clampNumber(double value, double minimum, double maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}

BOOL both(BOOL left, BOOL right) {
    return left && right;
}
