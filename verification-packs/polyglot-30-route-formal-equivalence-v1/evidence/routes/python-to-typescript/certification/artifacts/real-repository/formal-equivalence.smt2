; formal_input_digest: sha256:9c6af1b5f38ce1033c71d485814b709bef6ca89a7a290c7ec2d6b7f46094432b
; formal-input-sha256: sha256:9c6af1b5f38ce1033c71d485814b709bef6ca89a7a290c7ec2d6b7f46094432b
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:56f9cc8a3f5018f5eb370c9a59544aeacca1ad4e3b917f18f75d312198d73925
; independent-target-denotation-sha256: sha256:6af246fb419b79cc485f28bb4872eaa7f8db4900d12cc464b79c55cc0a15a09c
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
 (let ((?x143 (ubv_to_int source_left)))
 (let ((?x93 (ite (bvslt source_left (_ bv0 64)) (- ?x143 18446744073709551616) ?x143)))
 (and (>= ?x93 (- 9007199254740991)) (<= ?x93 9007199254740991)))))
(assert
 (let ((?x35 (ubv_to_int source_right)))
 (let ((?x321 (ite (bvslt source_right (_ bv0 64)) (- ?x35 18446744073709551616) ?x35)))
 (and (>= ?x321 (- 9007199254740991)) (<= ?x321 9007199254740991)))))
(assert
 (let ((?x56 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x393 ((_ extract 63 0) ?x56)))
 (let ((?x153 (ubv_to_int ?x393)))
 (let ((?x157 (ite (bvslt ?x393 (_ bv0 64)) (- ?x153 18446744073709551616) ?x153)))
 (and (>= ?x157 (- 9007199254740991)) (<= ?x157 9007199254740991)))))))
(assert
 false)
(check-sat)
