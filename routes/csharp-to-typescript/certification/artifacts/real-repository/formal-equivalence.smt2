; formal_input_digest: sha256:1ede444441fa93ffd515c6aab7068debce2cc09e8ebfcd972a390ce1623bb7a7
; formal-input-sha256: sha256:1ede444441fa93ffd515c6aab7068debce2cc09e8ebfcd972a390ce1623bb7a7
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
 (let ((?x41 (ubv_to_int source_left)))
 (let ((?x9 (ite (bvslt source_left (_ bv0 64)) (- ?x41 18446744073709551616) ?x41)))
 (and (>= ?x9 (- 9007199254740991)) (<= ?x9 9007199254740991)))))
(assert
 (let ((?x212 (ubv_to_int source_right)))
 (let ((?x102 (ite (bvslt source_right (_ bv0 64)) (- ?x212 18446744073709551616) ?x212)))
 (and (>= ?x102 (- 9007199254740991)) (<= ?x102 9007199254740991)))))
(assert
 (let ((?x131 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x236 ((_ extract 63 0) ?x131)))
 (let ((?x146 (ubv_to_int ?x236)))
 (let ((?x127 (ite (bvslt ?x236 (_ bv0 64)) (- ?x146 18446744073709551616) ?x146)))
 (and (>= ?x127 (- 9007199254740991)) (<= ?x127 9007199254740991)))))))
(assert
 false)
(check-sat)
