; formal_input_digest: sha256:d71bd86806e287c2b58f43227c64d2fe81501567fe21e35245b9d986f20fe24d
; formal-input-sha256: sha256:d71bd86806e287c2b58f43227c64d2fe81501567fe21e35245b9d986f20fe24d
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
 (let (($x5181 (and source_left source_right)))
 (let (($x680 (or $x5181 source_fallback)))
 (let ((?x209 (ite $x680 0 0)))
 (let ((?x3442 (ite $x5181 0 0)))
 (let ((?x527 (ite source_left 0 0)))
 (let (($x328 (and (distinct 0 0) true)))
 (let ((?x3383 (ite $x328 0 ?x527)))
 (let ((?x4588 (ite (and (distinct ?x3383 0) true) ?x3383 ?x3442)))
 (let ((?x269 (ite (and (distinct ?x4588 0) true) ?x4588 ?x209)))
 (= ?x269 0)))))))))))
(assert
 (let (($x5181 (and source_left source_right)))
 (let (($x680 (or $x5181 source_fallback)))
 (let ((?x209 (ite $x680 0 0)))
 (let ((?x3442 (ite $x5181 0 0)))
 (let ((?x527 (ite source_left 0 0)))
 (let (($x328 (and (distinct 0 0) true)))
 (let ((?x3383 (ite $x328 0 ?x527)))
 (let ((?x4588 (ite (and (distinct ?x3383 0) true) ?x3383 ?x3442)))
 (let ((?x269 (ite (and (distinct ?x4588 0) true) ?x4588 ?x209)))
 (= ?x269 0)))))))))))
(assert
 false)
(check-sat)
