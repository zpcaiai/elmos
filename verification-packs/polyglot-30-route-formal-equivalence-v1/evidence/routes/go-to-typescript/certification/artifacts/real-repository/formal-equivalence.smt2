; formal_input_digest: sha256:4b2e18e147a131195c1e7ff5f93a5badc62c64fbd71be3cb67b06dd737ddda42
; formal-input-sha256: sha256:4b2e18e147a131195c1e7ff5f93a5badc62c64fbd71be3cb67b06dd737ddda42
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
 (let ((?x59 (ubv_to_int source_left)))
 (let ((?x399 (ite (bvslt source_left (_ bv0 64)) (- ?x59 18446744073709551616) ?x59)))
 (and (>= ?x399 (- 9007199254740991)) (<= ?x399 9007199254740991)))))
(assert
 (let ((?x401 (ubv_to_int source_right)))
 (let ((?x66 (ite (bvslt source_right (_ bv0 64)) (- ?x401 18446744073709551616) ?x401)))
 (and (>= ?x66 (- 9007199254740991)) (<= ?x66 9007199254740991)))))
(assert
 (let ((?x142 (bvsub ((_ sign_extend 64) source_left) ((_ sign_extend 64) source_right))))
 (let ((?x309 ((_ extract 63 0) ?x142)))
 (let ((?x113 (ubv_to_int ?x309)))
 (let ((?x98 (ite (bvslt ?x309 (_ bv0 64)) (- ?x113 18446744073709551616) ?x113)))
 (and (>= ?x98 (- 9007199254740991)) (<= ?x98 9007199254740991)))))))
(assert
 false)
(check-sat)
