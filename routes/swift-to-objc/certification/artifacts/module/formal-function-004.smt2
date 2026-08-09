; formal_input_digest: sha256:169683a4ca9c0fb30e6e27dbca601b77ca5574047a44e8985ce42f885ad6e977
; formal-input-sha256: sha256:169683a4ca9c0fb30e6e27dbca601b77ca5574047a44e8985ce42f885ad6e977
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
 (let ((?x1694 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x4230 ((_ extract 63 0) ?x1694)))
 (let ((?x311 (ite (and (distinct ?x1694 ((_ sign_extend 64) ?x4230)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let ((?x1413 (ite $x680 ?x41 ?x311)))
 (= ?x1413 0))))))))
(assert
 (let ((?x1694 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x4230 ((_ extract 63 0) ?x1694)))
 (let ((?x311 (ite (and (distinct ?x1694 ((_ sign_extend 64) ?x4230)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let ((?x1413 (ite $x680 ?x41 ?x311)))
 (= ?x1413 0))))))))
(assert
 false)
(check-sat)
