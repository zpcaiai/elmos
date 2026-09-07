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

let actual0 = clamp(Int64(-10), Int64(0), Int64(100))
let expected0 = Int64(0)
if actual0 != expected0 { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\ti64-dec\t\(String(actual0))")
let actual1 = clamp(Int64(55), Int64(0), Int64(100))
let expected1 = Int64(55)
if actual1 != expected1 { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\ti64-dec\t\(String(actual1))")
let actual2 = clamp(Int64(101), Int64(0), Int64(100))
let expected2 = Int64(100)
if actual2 != expected2 { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\ti64-dec\t\(String(actual2))")
let actual3 = clamp(Int64(0), Int64(0), Int64(100))
let expected3 = Int64(0)
if actual3 != expected3 { fatalError("case 3") }
print("ELMOS_OBSERVATION\t3\ti64-dec\t\(String(actual3))")
let actual4 = clamp(Int64(100), Int64(0), Int64(100))
let expected4 = Int64(100)
if actual4 != expected4 { fatalError("case 4") }
print("ELMOS_OBSERVATION\t4\ti64-dec\t\(String(actual4))")
