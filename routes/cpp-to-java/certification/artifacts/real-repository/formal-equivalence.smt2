; formal_input_digest: sha256:9e85c886ebce444e7e28c98d6b7ce83ec45576a9391f8408ff9d4a65c2239fc6
; formal-input-sha256: sha256:9e85c886ebce444e7e28c98d6b7ce83ec45576a9391f8408ff9d4a65c2239fc6
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
 (let (($x22 (and source_left source_right)))
 (let (($x16 (or $x22 source_fallback)))
 (let ((?x12 (ite $x16 0 0)))
 (let ((?x14 (ite $x22 0 0)))
 (let ((?x20 (ite source_left 0 0)))
 (let (($x18 (and (distinct 0 0) true)))
 (let ((?x17 (ite $x18 0 ?x20)))
 (let ((?x21 (ite (and (distinct ?x17 0) true) ?x17 ?x14)))
 (let ((?x55 (ite (and (distinct ?x21 0) true) ?x21 ?x12)))
 (= ?x55 0)))))))))))
(assert
 (let (($x22 (and source_left source_right)))
 (let (($x16 (or $x22 source_fallback)))
 (let ((?x12 (ite $x16 0 0)))
 (let ((?x14 (ite $x22 0 0)))
 (let ((?x20 (ite source_left 0 0)))
 (let (($x18 (and (distinct 0 0) true)))
 (let ((?x17 (ite $x18 0 ?x20)))
 (let ((?x21 (ite (and (distinct ?x17 0) true) ?x17 ?x14)))
 (let ((?x55 (ite (and (distinct ?x21 0) true) ?x21 ?x12)))
 (= ?x55 0)))))))))))
(assert
 false)
(check-sat)
