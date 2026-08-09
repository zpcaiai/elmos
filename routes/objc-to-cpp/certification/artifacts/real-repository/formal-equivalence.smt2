; formal_input_digest: sha256:5b906097ccbcd3145a4bc3da063a34da994aed34ecb9d32a5c3baedecfdc87c0
; formal-input-sha256: sha256:5b906097ccbcd3145a4bc3da063a34da994aed34ecb9d32a5c3baedecfdc87c0
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:0dd944dcf94a81a7ed79dadb6f75777a3922dbecbcc09db96d01e6a7c8985293
; independent-target-denotation-sha256: sha256:f095d0796a33a69ec66c6f624ea0c759d2d03be79b8e41ab2a5a16ca7f29df0d
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_left () Bool)
(declare-fun source_left () Bool)
(declare-fun target_right () Bool)
(declare-fun source_right () Bool)
(declare-fun target_fallback () Bool)
(declare-fun source_fallback () Bool)
(assert
 (= source_left target_left))
(assert
 (= source_right target_right))
(assert
 (= source_fallback target_fallback))
(assert
 (let (($x51 (and source_left source_right)))
 (let (($x1694 (or $x51 source_fallback)))
 (let ((?x73 (ite $x1694 0 0)))
 (let ((?x165 (ite $x51 0 0)))
 (let ((?x963 (ite source_left 0 0)))
 (let (($x163 (and (distinct 0 0) true)))
 (let ((?x172 (ite $x163 0 ?x963)))
 (let ((?x16 (ite (and (distinct ?x172 0) true) ?x172 ?x165)))
 (let ((?x21 (ite (and (distinct ?x16 0) true) ?x16 ?x73)))
 (= ?x21 0)))))))))))
(assert
 (let (($x51 (and source_left source_right)))
 (let (($x1694 (or $x51 source_fallback)))
 (let ((?x73 (ite $x1694 0 0)))
 (let ((?x165 (ite $x51 0 0)))
 (let ((?x963 (ite source_left 0 0)))
 (let (($x163 (and (distinct 0 0) true)))
 (let ((?x172 (ite $x163 0 ?x963)))
 (let ((?x16 (ite (and (distinct ?x172 0) true) ?x172 ?x165)))
 (let ((?x21 (ite (and (distinct ?x16 0) true) ?x16 ?x73)))
 (= ?x21 0)))))))))))
(assert
 false)
(check-sat)
