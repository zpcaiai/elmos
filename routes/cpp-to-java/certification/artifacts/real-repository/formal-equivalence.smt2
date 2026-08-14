; formal_input_digest: sha256:c2fb0f166745cb810d6d12184dbd5617c48e8c99f7a30a6cc122dfa42b0749da
; formal-input-sha256: sha256:c2fb0f166745cb810d6d12184dbd5617c48e8c99f7a30a6cc122dfa42b0749da
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
 (let (($x4650 (and source_left source_right)))
 (let (($x3419 (or $x4650 source_fallback)))
 (let ((?x41 (ite $x3419 0 0)))
 (let ((?x2867 (ite $x4650 0 0)))
 (let ((?x3614 (ite source_left 0 0)))
 (let (($x2439 (and (distinct 0 0) true)))
 (let ((?x3766 (ite $x2439 0 ?x3614)))
 (let ((?x680 (ite (and (distinct ?x3766 0) true) ?x3766 ?x2867)))
 (let ((?x4588 (ite (and (distinct ?x680 0) true) ?x680 ?x41)))
 (= ?x4588 0)))))))))))
(assert
 (let (($x4650 (and source_left source_right)))
 (let (($x3419 (or $x4650 source_fallback)))
 (let ((?x41 (ite $x3419 0 0)))
 (let ((?x2867 (ite $x4650 0 0)))
 (let ((?x3614 (ite source_left 0 0)))
 (let (($x2439 (and (distinct 0 0) true)))
 (let ((?x3766 (ite $x2439 0 ?x3614)))
 (let ((?x680 (ite (and (distinct ?x3766 0) true) ?x3766 ?x2867)))
 (let ((?x4588 (ite (and (distinct ?x680 0) true) ?x680 ?x41)))
 (= ?x4588 0)))))))))))
(assert
 false)
(check-sat)
