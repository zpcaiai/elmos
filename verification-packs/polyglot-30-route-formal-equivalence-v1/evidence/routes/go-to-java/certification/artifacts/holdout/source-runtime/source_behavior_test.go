package holdout

import (
    "encoding/base64"
    "fmt"
    "testing"
)

func TestElmosSourceBehavior(t *testing.T) {
    actual0 := clamp(20, 10)
    if actual0 != 10 { t.Fatalf("case 0") }
    fmt.Printf("ELMOS_OBSERVATION\t0\tb64\t%s\n", base64.StdEncoding.EncodeToString([]byte(fmt.Sprint(actual0))))
    actual1 := clamp(-2, 10)
    if actual1 != 0 { t.Fatalf("case 1") }
    fmt.Printf("ELMOS_OBSERVATION\t1\tb64\t%s\n", base64.StdEncoding.EncodeToString([]byte(fmt.Sprint(actual1))))
    actual2 := clamp(7, 10)
    if actual2 != 7 { t.Fatalf("case 2") }
    fmt.Printf("ELMOS_OBSERVATION\t2\tb64\t%s\n", base64.StdEncoding.EncodeToString([]byte(fmt.Sprint(actual2))))
}
