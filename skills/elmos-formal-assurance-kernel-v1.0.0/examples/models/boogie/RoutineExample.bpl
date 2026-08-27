procedure Reserve(balance: int, reserved: int, amount: int)
  requires balance >= 0;
  requires reserved >= 0;
  requires amount >= 0;
  requires amount <= balance;
  returns (newBalance: int, newReserved: int);
  ensures newBalance >= 0;
  ensures newBalance == balance - amount;
  ensures newReserved == reserved + amount;
  ensures newBalance + newReserved == balance + reserved;
{
  newBalance := balance - amount;
  newReserved := reserved + amount;
}
