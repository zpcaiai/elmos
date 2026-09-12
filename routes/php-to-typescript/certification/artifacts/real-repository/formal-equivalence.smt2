; formal_input_digest: sha256:6be7545105cfcc0c9d01f89b9e11be6f0302ae9725764f85d1d9100e22546067
; formal-input-sha256: sha256:6be7545105cfcc0c9d01f89b9e11be6f0302ae9725764f85d1d9100e22546067
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
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
 (let ((?x123 (ubv_to_int source_left)))
 (let ((?x147 (ite (bvslt source_left (_ bv0 64)) (- ?x123 18446744073709551616) ?x123)))
 (and (>= ?x147 (- 9007199254740991)) (<= ?x147 9007199254740991)))))
(assert
 (let ((?x113 (ubv_to_int source_right)))
 (let ((?x117 (ite (bvslt source_right (_ bv0 64)) (- ?x113 18446744073709551616) ?x113)))
 (and (>= ?x117 (- 9007199254740991)) (<= ?x117 9007199254740991)))))
(assert
 (let ((?x37 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x34 ((_ extract 63 0) ?x37)))
 (let ((?x111 (ubv_to_int ?x34)))
 (let ((?x98 (ite (bvslt ?x34 (_ bv0 64)) (- ?x111 18446744073709551616) ?x111)))
 (and (>= ?x98 (- 9007199254740991)) (<= ?x98 9007199254740991)))))))
(assert
 (let ((?x37 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x34 ((_ extract 63 0) ?x37)))
 (let ((?x89 (ite (and (distinct ?x37 ((_ sign_extend 64) ?x34)) true) 1 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x96 (bvslt source_left source_right)))
 (let ((?x33 (ite $x96 0 (ite $x38 ?x29 ?x89))))
 (let ((?x1382 (ite $x38 ?x29 ?x33)))
 (= ?x1382 0))))))))))
(assert
 (let ((?x37 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x34 ((_ extract 63 0) ?x37)))
 (let ((?x89 (ite (and (distinct ?x37 ((_ sign_extend 64) ?x34)) true) 1 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x96 (bvslt source_left source_right)))
 (let ((?x33 (ite $x96 0 (ite $x38 ?x29 ?x89))))
 (let ((?x1382 (ite $x38 ?x29 ?x33)))
 (= ?x1382 0))))))))))
(assert
 false)
(check-sat)
