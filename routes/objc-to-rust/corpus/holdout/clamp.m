#import <Foundation/Foundation.h>

long long clamp(long long value, long long upper) {
    if (value > upper) {
        return upper;
    }
    if (value < 0) {
        return 0;
    }
    return value;
}
