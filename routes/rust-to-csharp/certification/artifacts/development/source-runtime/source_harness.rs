include!("pricing.rs");

fn main() {
    let actual_0 = calculate(100, 20);
    assert!(actual_0 == 120, "case 0");
    println!("ELMOS_OBSERVATION\t0\trust-debug\t{:?}", actual_0);
    let actual_1 = calculate(-1, 5);
    assert!(actual_1 == 0, "case 1");
    println!("ELMOS_OBSERVATION\t1\trust-debug\t{:?}", actual_1);
    let actual_2 = calculate(7, -2);
    assert!(actual_2 == 5, "case 2");
    println!("ELMOS_OBSERVATION\t2\trust-debug\t{:?}", actual_2);
}
