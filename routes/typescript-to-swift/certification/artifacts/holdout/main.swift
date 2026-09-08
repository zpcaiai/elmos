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

let actual0 = elmos_fn_87c620e7ad318001(20.0, 10.0)
let expected0 = 10.0
if !elmosHarnessSameFP64(actual0, expected0) { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\tfp64-hex\t\(elmosHarnessFP64(actual0))")
let actual1 = elmos_fn_87c620e7ad318001(-2.0, 10.0)
let expected1 = 0.0
if !elmosHarnessSameFP64(actual1, expected1) { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\tfp64-hex\t\(elmosHarnessFP64(actual1))")
let actual2 = elmos_fn_87c620e7ad318001(7.0, 10.0)
let expected2 = 7.0
if !elmosHarnessSameFP64(actual2, expected2) { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\tfp64-hex\t\(elmosHarnessFP64(actual2))")
