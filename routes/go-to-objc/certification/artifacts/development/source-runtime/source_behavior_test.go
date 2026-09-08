package pricing

import (
    _elmosBase64 "encoding/base64"
    _elmosFmt "fmt"
    _elmosTesting "testing"
)

func TestElmosSourceBehavior(_elmosT *_elmosTesting.T) {
    actual0 := calculate(100, 20)
    if actual0 != 120 { _elmosT.Fatalf("case 0") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t0\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual0))))
    actual1 := calculate(-1, 5)
    if actual1 != 0 { _elmosT.Fatalf("case 1") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t1\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual1))))
    actual2 := calculate(7, -2)
    if actual2 != 5 { _elmosT.Fatalf("case 2") }
    _elmosFmt.Printf("ELMOS_OBSERVATION\t2\tb64\t%s\n", _elmosBase64.StdEncoding.EncodeToString([]byte(_elmosFmt.Sprint(actual2))))
}
