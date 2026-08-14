; formal_input_digest: sha256:c0c814ae5258f496ae884c01f3ca93882b7f52f0c99e3c141436c7ce28a25328
; formal-input-sha256: sha256:c0c814ae5258f496ae884c01f3ca93882b7f52f0c99e3c141436c7ce28a25328
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
 (let ((?x77 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x4010 ((_ extract 63 0) ?x77)))
 (let ((?x826 (ite (and (distinct ?x77 ((_ sign_extend 64) ?x4010)) true) 1 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let ((?x3096 (ite $x56 ?x3383 ?x826)))
 (= ?x3096 0))))))))
(assert
 (let ((?x77 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x4010 ((_ extract 63 0) ?x77)))
 (let ((?x826 (ite (and (distinct ?x77 ((_ sign_extend 64) ?x4010)) true) 1 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let ((?x3096 (ite $x56 ?x3383 ?x826)))
 (= ?x3096 0))))))))
(assert
 false)
(check-sat)
