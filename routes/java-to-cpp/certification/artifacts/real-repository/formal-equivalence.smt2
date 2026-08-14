; formal_input_digest: sha256:5d936a283af7384080a9224db779c9b614c6e72ccf27517f18cb855b64784343
; formal-input-sha256: sha256:5d936a283af7384080a9224db779c9b614c6e72ccf27517f18cb855b64784343
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
 (let (($x5142 (and source_left source_right)))
 (let (($x56 (or $x5142 source_fallback)))
 (let ((?x4989 (ite $x56 0 0)))
 (let ((?x365 (ite $x5142 0 0)))
 (let ((?x4712 (ite source_left 0 0)))
 (let (($x3044 (and (distinct 0 0) true)))
 (let ((?x814 (ite $x3044 0 ?x4712)))
 (let ((?x3419 (ite (and (distinct ?x814 0) true) ?x814 ?x365)))
 (let ((?x680 (ite (and (distinct ?x3419 0) true) ?x3419 ?x4989)))
 (= ?x680 0)))))))))))
(assert
 (let (($x5142 (and source_left source_right)))
 (let (($x56 (or $x5142 source_fallback)))
 (let ((?x4989 (ite $x56 0 0)))
 (let ((?x365 (ite $x5142 0 0)))
 (let ((?x4712 (ite source_left 0 0)))
 (let (($x3044 (and (distinct 0 0) true)))
 (let ((?x814 (ite $x3044 0 ?x4712)))
 (let ((?x3419 (ite (and (distinct ?x814 0) true) ?x814 ?x365)))
 (let ((?x680 (ite (and (distinct ?x3419 0) true) ?x3419 ?x4989)))
 (= ?x680 0)))))))))))
(assert
 false)
(check-sat)
