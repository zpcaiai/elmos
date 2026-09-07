pub fn reserve(balance: u64, amount: u64) -> Option<u64> {
    balance.checked_sub(amount)
}

#[cfg(kani)]
#[kani::proof]
fn elmos_proof() {
    let balance: u64 = kani::any();
    let amount: u64 = kani::any();
    kani::assume(amount <= balance);
    let result = reserve(balance, amount).unwrap();
    assert!(result <= balance);
    assert_eq!(result + amount, balance);
}
