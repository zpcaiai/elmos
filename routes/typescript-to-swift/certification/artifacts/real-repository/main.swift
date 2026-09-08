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

let actual0 = elmos_fn_09debc29700683c3(20.0, 7.0)
let expected0 = 13.0
if !elmosHarnessSameFP64(actual0, expected0) { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\tfp64-hex\t\(elmosHarnessFP64(actual0))")
let actual1 = elmos_fn_09debc29700683c3(3.0, 8.0)
let expected1 = 0.0
if !elmosHarnessSameFP64(actual1, expected1) { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\tfp64-hex\t\(elmosHarnessFP64(actual1))")
let actual2 = elmos_fn_09debc29700683c3(4.0, 4.0)
let expected2 = 0.0
if !elmosHarnessSameFP64(actual2, expected2) { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\tfp64-hex\t\(elmosHarnessFP64(actual2))")
