#import <Foundation/Foundation.h>

long long calculate(long long subtotal, long long tax) {
    if (subtotal < 0) {
        return 0;
    }
    return subtotal + tax;
}
