; formal_input_digest: sha256:60398ab3f043f32d5e75c28c727a995aea473ef03d63b8ef949b78b41b9caf26
; formal-input-sha256: sha256:60398ab3f043f32d5e75c28c727a995aea473ef03d63b8ef949b78b41b9caf26
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
 (let ((?x380 (ubv_to_int source_left)))
 (let ((?x308 (ite (bvslt source_left (_ bv0 64)) (- ?x380 18446744073709551616) ?x380)))
 (and (>= ?x308 (- 9007199254740991)) (<= ?x308 9007199254740991)))))
(assert
 (let ((?x312 (ubv_to_int source_right)))
 (let ((?x254 (ite (bvslt source_right (_ bv0 64)) (- ?x312 18446744073709551616) ?x312)))
 (and (>= ?x254 (- 9007199254740991)) (<= ?x254 9007199254740991)))))
(assert
 (let ((?x5 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x461 ((_ extract 63 0) ?x5)))
 (let ((?x68 (ubv_to_int ?x461)))
 (let ((?x125 (ite (bvslt ?x461 (_ bv0 64)) (- ?x68 18446744073709551616) ?x68)))
 (and (>= ?x125 (- 9007199254740991)) (<= ?x125 9007199254740991)))))))
(assert
 false)
(check-sat)
