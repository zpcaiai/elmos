typedef signed char BOOL;
@interface NSString
- (BOOL)isEqualToString:(NSString *)other;
@end
BOOL same(NSString *left, NSString *right) { return left == right; }
