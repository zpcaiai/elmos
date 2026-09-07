; formal_input_digest: sha256:34468a6b558341f1956cc6c2cc9b39204a9627fc7b13366a9bcf153a0c5cfec3
; formal-input-sha256: sha256:34468a6b558341f1956cc6c2cc9b39204a9627fc7b13366a9bcf153a0c5cfec3
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
 (let ((?x24 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x155 ((_ extract 63 0) ?x24)))
 (let ((?x79 (ite (and (distinct ?x24 ((_ sign_extend 64) ?x155)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let ((?x92 (ite $x1694 ?x67 ?x79)))
 (= ?x92 0))))))))
(assert
 (let ((?x24 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x155 ((_ extract 63 0) ?x24)))
 (let ((?x79 (ite (and (distinct ?x24 ((_ sign_extend 64) ?x155)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let ((?x92 (ite $x1694 ?x67 ?x79)))
 (= ?x92 0))))))))
(assert
 false)
(check-sat)
