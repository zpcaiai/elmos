include!("migrated.rs");

fn main() {
    let actual_0 = difference(20, 7);
    assert!(actual_0 == 13, "case 0");
    println!("ELMOS_OBSERVATION\t0\trust-debug\t{:?}", actual_0);
    let actual_1 = difference(3, 8);
    assert!(actual_1 == 0, "case 1");
    println!("ELMOS_OBSERVATION\t1\trust-debug\t{:?}", actual_1);
    let actual_2 = difference(4, 4);
    assert!(actual_2 == 0, "case 2");
    println!("ELMOS_OBSERVATION\t2\trust-debug\t{:?}", actual_2);
}
