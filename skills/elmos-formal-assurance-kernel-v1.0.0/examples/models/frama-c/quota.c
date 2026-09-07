#include <stdint.h>

/*@ requires amount <= balance;
    assigns \nothing;
    ensures \result == balance - amount;
    ensures \result <= balance;
*/
uint64_t reserve(uint64_t balance, uint64_t amount) {
  return balance - amount;
}
