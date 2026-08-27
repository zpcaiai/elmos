method Reserve(balance: nat, reserved: nat, amount: nat)
  requires amount <= balance
  returns (newBalance: nat, newReserved: nat)
  ensures newBalance == balance - amount
  ensures newReserved == reserved + amount
  ensures newBalance + newReserved == balance + reserved
{
  newBalance := balance - amount;
  newReserved := reserved + amount;
}

method RetryLoop(maxAttempts: nat) returns (attempts: nat)
  ensures attempts <= maxAttempts
{
  attempts := 0;
  while attempts < maxAttempts
    invariant 0 <= attempts <= maxAttempts
    decreases maxAttempts - attempts
  {
    attempts := attempts + 1;
  }
}
