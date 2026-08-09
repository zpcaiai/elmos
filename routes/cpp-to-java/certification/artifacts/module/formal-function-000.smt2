; formal_input_digest: sha256:5f035c43a00c6d6e5db10cb73db8cf6bca50dd8a6c85ef4c6fea765d40357895
; formal-input-sha256: sha256:5f035c43a00c6d6e5db10cb73db8cf6bca50dd8a6c85ef4c6fea765d40357895
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
 (let ((?x3614 (ite source_left 0 0)))
 (let (($x2439 (and (distinct 0 0) true)))
 (let ((?x3766 (ite $x2439 0 ?x3614)))
 (= ?x3766 0)))))
(assert
 (let ((?x3614 (ite source_left 0 0)))
 (let (($x2439 (and (distinct 0 0) true)))
 (let ((?x3766 (ite $x2439 0 ?x3614)))
 (= ?x3766 0)))))
(assert
 false)
(check-sat)
