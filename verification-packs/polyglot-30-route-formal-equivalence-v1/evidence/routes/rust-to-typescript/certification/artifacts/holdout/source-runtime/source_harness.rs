include!("clamp.rs");

fn main() {
    let actual_0 = clamp(20, 10);
    assert!(actual_0 == 10, "case 0");
    println!("ELMOS_OBSERVATION\t0\trust-debug\t{:?}", actual_0);
    let actual_1 = clamp(-2, 10);
    assert!(actual_1 == 0, "case 1");
    println!("ELMOS_OBSERVATION\t1\trust-debug\t{:?}", actual_1);
    let actual_2 = clamp(7, 10);
    assert!(actual_2 == 7, "case 2");
    println!("ELMOS_OBSERVATION\t2\trust-debug\t{:?}", actual_2);
}
