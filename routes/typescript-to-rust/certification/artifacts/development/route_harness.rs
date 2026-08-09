include!("migrated.rs");

fn main() {
    let actual_0 = calculate(100.0, 20.0);
    assert!(actual_0 == 120.0, "case 0");
    println!("ELMOS_OBSERVATION\t0\trust-debug\t{:?}", actual_0);
    let actual_1 = calculate(-1.0, 5.0);
    assert!(actual_1 == 0.0, "case 1");
    println!("ELMOS_OBSERVATION\t1\trust-debug\t{:?}", actual_1);
    let actual_2 = calculate(7.0, -2.0);
    assert!(actual_2 == 5.0, "case 2");
    println!("ELMOS_OBSERVATION\t2\trust-debug\t{:?}", actual_2);
}
