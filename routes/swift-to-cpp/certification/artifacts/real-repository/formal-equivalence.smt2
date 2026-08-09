; formal_input_digest: sha256:3b052cadc84ed6f9dab04d2a351b181d85ba79943224398cd82c14fdd46e05c0
; formal-input-sha256: sha256:3b052cadc84ed6f9dab04d2a351b181d85ba79943224398cd82c14fdd46e05c0
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
 (let (($x2044 (and source_left source_right)))
 (let (($x269 (or $x2044 source_fallback)))
 (let ((?x178 (ite $x269 0 0)))
 (let ((?x4915 (ite $x2044 0 0)))
 (let ((?x25 (ite source_left 0 0)))
 (let (($x77 (and (distinct 0 0) true)))
 (let ((?x203 (ite $x77 0 ?x25)))
 (let ((?x1187 (ite (and (distinct ?x203 0) true) ?x203 ?x4915)))
 (let ((?x1694 (ite (and (distinct ?x1187 0) true) ?x1187 ?x178)))
 (= ?x1694 0)))))))))))
(assert
 (let (($x2044 (and source_left source_right)))
 (let (($x269 (or $x2044 source_fallback)))
 (let ((?x178 (ite $x269 0 0)))
 (let ((?x4915 (ite $x2044 0 0)))
 (let ((?x25 (ite source_left 0 0)))
 (let (($x77 (and (distinct 0 0) true)))
 (let ((?x203 (ite $x77 0 ?x25)))
 (let ((?x1187 (ite (and (distinct ?x203 0) true) ?x203 ?x4915)))
 (let ((?x1694 (ite (and (distinct ?x1187 0) true) ?x1187 ?x178)))
 (= ?x1694 0)))))))))))
(assert
 false)
(check-sat)
