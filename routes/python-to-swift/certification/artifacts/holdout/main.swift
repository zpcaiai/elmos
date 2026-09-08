import Foundation

func elmosHarnessSameFP64(_ left: Double, _ right: Double) -> Bool {
    return (left.isNaN && right.isNaN) || left.bitPattern == right.bitPattern
}

func elmosHarnessFP64(_ value: Double) -> String {
    return String(format: "%016llx", value.bitPattern)
}

func elmosHarnessHexUTF8(_ value: String) -> String {
    return value.utf8.map { String(format: "%02x", $0) }.joined()
}

let actual0 = elmos_fn_ba3639d94478f297(Int64(20), Int64(10))
let expected0 = Int64(10)
if actual0 != expected0 { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\ti64-dec\t\(String(actual0))")
let actual1 = elmos_fn_ba3639d94478f297(Int64(-2), Int64(10))
let expected1 = Int64(0)
if actual1 != expected1 { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\ti64-dec\t\(String(actual1))")
let actual2 = elmos_fn_ba3639d94478f297(Int64(7), Int64(10))
let expected2 = Int64(7)
if actual2 != expected2 { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\ti64-dec\t\(String(actual2))")
