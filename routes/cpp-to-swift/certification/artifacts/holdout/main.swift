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

let actual0 = echoNumber(-0.0)
let expected0 = -0.0
if !elmosHarnessSameFP64(actual0, expected0) { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\tfp64-hex\t\(elmosHarnessFP64(actual0))")
let actual1 = echoNumber(0.0)
let expected1 = 0.0
if !elmosHarnessSameFP64(actual1, expected1) { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\tfp64-hex\t\(elmosHarnessFP64(actual1))")
let actual2 = echoNumber(1.7976931348623157e+308)
let expected2 = 1.7976931348623157e+308
if !elmosHarnessSameFP64(actual2, expected2) { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\tfp64-hex\t\(elmosHarnessFP64(actual2))")
let actual3 = echoNumber(-1.7976931348623157e+308)
let expected3 = -1.7976931348623157e+308
if !elmosHarnessSameFP64(actual3, expected3) { fatalError("case 3") }
print("ELMOS_OBSERVATION\t3\tfp64-hex\t\(elmosHarnessFP64(actual3))")
let actual4 = echoNumber(2.2250738585072014e-308)
let expected4 = 2.2250738585072014e-308
if !elmosHarnessSameFP64(actual4, expected4) { fatalError("case 4") }
print("ELMOS_OBSERVATION\t4\tfp64-hex\t\(elmosHarnessFP64(actual4))")
