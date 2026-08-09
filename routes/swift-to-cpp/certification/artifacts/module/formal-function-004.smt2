; formal_input_digest: sha256:5a22aed4cb9924fa360c22e4c6ae63b171f2c37804dae2674a948cac5d425d2e
; formal-input-sha256: sha256:5a22aed4cb9924fa360c22e4c6ae63b171f2c37804dae2674a948cac5d425d2e
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-function-004-input.json
; independent-source-denotation-sha256: sha256:a421c8d48182015667427029ceb5ec02e8a49f68e6ff3a61d6b70c40290fd7b5
; independent-target-denotation-sha256: sha256:a41f0bb44704138bbd2e99c8bcd2a4ea6de1e4b1cf22572b6a1ee4b4340b7a1e
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_left () (_ BitVec 64))
(declare-fun source_left () (_ BitVec 64))
(declare-fun target_right () (_ BitVec 64))
(declare-fun source_right () (_ BitVec 64))
(assert
 (= source_left target_left))
(assert
 (= source_right target_right))
(assert
 (let ((?x1300 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x271 ((_ extract 63 0) ?x1300)))
 (let ((?x5217 (ite (and (distinct ?x1300 ((_ sign_extend 64) ?x271)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let ((?x41 (ite $x269 ?x79 ?x5217)))
 (= ?x41 0))))))))
(assert
 (let ((?x1300 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x271 ((_ extract 63 0) ?x1300)))
 (let ((?x5217 (ite (and (distinct ?x1300 ((_ sign_extend 64) ?x271)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let ((?x41 (ite $x269 ?x79 ?x5217)))
 (= ?x41 0))))))))
(assert
 false)
(check-sat)
