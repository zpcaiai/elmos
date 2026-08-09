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

let actual0 = clampNumber(-10.5, 0.0, 100.0)
let expected0 = 0.0
if !elmosHarnessSameFP64(actual0, expected0) { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\tfp64-hex\t\(elmosHarnessFP64(actual0))")
let actual1 = clampNumber(55.25, 0.0, 100.0)
let expected1 = 55.25
if !elmosHarnessSameFP64(actual1, expected1) { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\tfp64-hex\t\(elmosHarnessFP64(actual1))")
let actual2 = clampNumber(101.5, 0.0, 100.0)
let expected2 = 100.0
if !elmosHarnessSameFP64(actual2, expected2) { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\tfp64-hex\t\(elmosHarnessFP64(actual2))")
let actual3 = clampNumber(-0.0, -1.0, 1.0)
let expected3 = -0.0
if !elmosHarnessSameFP64(actual3, expected3) { fatalError("case 3") }
print("ELMOS_OBSERVATION\t3\tfp64-hex\t\(elmosHarnessFP64(actual3))")
let actual4 = clampNumber(0.0, -0.0, 1.0)
let expected4 = 0.0
if !elmosHarnessSameFP64(actual4, expected4) { fatalError("case 4") }
print("ELMOS_OBSERVATION\t4\tfp64-hex\t\(elmosHarnessFP64(actual4))")
