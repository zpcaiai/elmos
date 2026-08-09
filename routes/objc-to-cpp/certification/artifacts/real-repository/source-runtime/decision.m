#import <Foundation/Foundation.h>
BOOL decision(BOOL left, BOOL right, BOOL fallback) {
    if ((left && right) || fallback) { return YES; }
    return NO;
}
