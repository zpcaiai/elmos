; formal_input_digest: sha256:1e2a4c769b94dab4b6cb17368d61f3e02990d5ee965b8f4410e250b7d3360c51
; formal-input-sha256: sha256:1e2a4c769b94dab4b6cb17368d61f3e02990d5ee965b8f4410e250b7d3360c51
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-function-000-input.json
; independent-source-denotation-sha256: sha256:6f2a21b2edd2a1d48fcbcc6bd4d271a2077f4d2a6f839a5db112f8a84fface11
; independent-target-denotation-sha256: sha256:fbc704eaa618ba2a9adae6bf6ac0d2ee3b92aa7b8ae431e5d1937b33c509f8dc
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_left () Bool)
(declare-fun source_left () Bool)
(declare-fun target_right () Bool)
(declare-fun source_right () Bool)
(assert
 (= source_left target_left))
(assert
 (= source_right target_right))
(assert
 (let ((?x25 (ite source_left 0 0)))
 (let (($x77 (and (distinct 0 0) true)))
 (let ((?x203 (ite $x77 0 ?x25)))
 (= ?x203 0)))))
(assert
 (let ((?x25 (ite source_left 0 0)))
 (let (($x77 (and (distinct 0 0) true)))
 (let ((?x203 (ite $x77 0 ?x25)))
 (= ?x203 0)))))
(assert
 false)
(check-sat)
