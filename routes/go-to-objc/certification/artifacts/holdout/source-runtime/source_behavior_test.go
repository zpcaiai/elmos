package holdout

import (
    _elmosBase64 "encoding/base64"
    _elmosFmt "fmt"
    _elmosTesting "testing"
)

func TestElmosSourceBehavior(_elmosT *_elmosTesting.T) {
    actual0 := clamp(20, 10)
    if actual0 != 10 { _elmosT.Fatalf("case 0") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t0\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual0))))
    actual1 := clamp(-2, 10)
    if actual1 != 0 { _elmosT.Fatalf("case 1") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t1\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual1))))
    actual2 := clamp(7, 10)
    if actual2 != 7 { _elmosT.Fatalf("case 2") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t2\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual2))))
}
