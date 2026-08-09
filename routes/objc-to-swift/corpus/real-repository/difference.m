#import <Foundation/Foundation.h>

long long difference(long long left, long long right) {
    if (left < right) {
        return 0;
    }
    return left - right;
}
