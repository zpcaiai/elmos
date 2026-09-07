; formal_input_digest: sha256:86ca3acb21ab14c86275fdd6e47f03b5b724d7f51de05f1856a5a267518dc7bd
; formal-input-sha256: sha256:86ca3acb21ab14c86275fdd6e47f03b5b724d7f51de05f1856a5a267518dc7bd
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
 (let ((?x107 (ite (bvslt source_left (_ bv0 64)) (- ?x143 18446744073709551616) ?x143)))
 (and (>= ?x107 (- 9007199254740991)) (<= ?x107 9007199254740991)))))
(assert
 (let ((?x109 (ubv_to_int source_right)))
 (let ((?x69 (ite (bvslt source_right (_ bv0 64)) (- ?x109 18446744073709551616) ?x109)))
 (and (>= ?x69 (- 9007199254740991)) (<= ?x69 9007199254740991)))))
(assert
 (let ((?x30 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x23 ((_ extract 63 0) ?x30)))
 (let ((?x80 (ubv_to_int ?x23)))
 (let ((?x147 (ite (bvslt ?x23 (_ bv0 64)) (- ?x80 18446744073709551616) ?x80)))
 (and (>= ?x147 (- 9007199254740991)) (<= ?x147 9007199254740991)))))))
(assert
 false)
(check-sat)
