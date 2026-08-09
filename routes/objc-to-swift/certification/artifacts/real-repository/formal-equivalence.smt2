; formal_input_digest: sha256:8cbda4231a3fc8e4e33eb2d73686b766c5ffa11d76d8179864386c5c505bc972
; formal-input-sha256: sha256:8cbda4231a3fc8e4e33eb2d73686b766c5ffa11d76d8179864386c5c505bc972
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
 (let (($x3436 (and source_left source_right)))
 (let (($x4588 (or $x3436 source_fallback)))
 (let ((?x79 (ite $x4588 0 0)))
 (let ((?x1703 (ite $x3436 0 0)))
 (let ((?x2756 (ite source_left 0 0)))
 (let (($x4183 (and (distinct 0 0) true)))
 (let ((?x51 (ite $x4183 0 ?x2756)))
 (let ((?x269 (ite (and (distinct ?x51 0) true) ?x51 ?x1703)))
 (let ((?x1187 (ite (and (distinct ?x269 0) true) ?x269 ?x79)))
 (= ?x1187 0)))))))))))
(assert
 (let (($x3436 (and source_left source_right)))
 (let (($x4588 (or $x3436 source_fallback)))
 (let ((?x79 (ite $x4588 0 0)))
 (let ((?x1703 (ite $x3436 0 0)))
 (let ((?x2756 (ite source_left 0 0)))
 (let (($x4183 (and (distinct 0 0) true)))
 (let ((?x51 (ite $x4183 0 ?x2756)))
 (let ((?x269 (ite (and (distinct ?x51 0) true) ?x51 ?x1703)))
 (let ((?x1187 (ite (and (distinct ?x269 0) true) ?x269 ?x79)))
 (= ?x1187 0)))))))))))
(assert
 false)
(check-sat)
