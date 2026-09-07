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

let actual0 = both(true, true)
let expected0 = true
if actual0 != expected0 { fatalError("case 0") }
print("ELMOS_OBSERVATION\t0\tbool\t\((actual0 ? "true" : "false"))")
let actual1 = both(true, false)
let expected1 = false
if actual1 != expected1 { fatalError("case 1") }
print("ELMOS_OBSERVATION\t1\tbool\t\((actual1 ? "true" : "false"))")
let actual2 = both(false, true)
let expected2 = false
if actual2 != expected2 { fatalError("case 2") }
print("ELMOS_OBSERVATION\t2\tbool\t\((actual2 ? "true" : "false"))")
let actual3 = both(false, false)
let expected3 = false
if actual3 != expected3 { fatalError("case 3") }
print("ELMOS_OBSERVATION\t3\tbool\t\((actual3 ? "true" : "false"))")
