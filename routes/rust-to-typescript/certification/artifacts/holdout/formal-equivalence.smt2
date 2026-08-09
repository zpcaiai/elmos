; formal_input_digest: sha256:822ea69d1b6d1f063f2551521dd7b93c43d5fb943a2da623f24a5eed0451f74f
; formal-input-sha256: sha256:822ea69d1b6d1f063f2551521dd7b93c43d5fb943a2da623f24a5eed0451f74f
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:ee96d38c7aad66a1823c67e1819d6c6f93f617e999eeeefd680098cd1ae7ac2d
; independent-target-denotation-sha256: sha256:4f9b88b79aa5340ae29ed06de88288e849881d3b4e03c5763ca4fe2fcfc7a9d7
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ BitVec 64))
(declare-fun source_value () (_ BitVec 64))
(declare-fun target_upper () (_ BitVec 64))
(declare-fun source_upper () (_ BitVec 64))
(assert
 (= source_value target_value))
(assert
 (= source_upper target_upper))
(assert
 (let ((?x22 (ubv_to_int source_value)))
 (let ((?x286 (ite (bvslt source_value (_ bv0 64)) (- ?x22 18446744073709551616) ?x22)))
 (and (>= ?x286 (- 9007199254740991)) (<= ?x286 9007199254740991)))))
(assert
 (let ((?x104 (ubv_to_int source_upper)))
 (let ((?x66 (ite (bvslt source_upper (_ bv0 64)) (- ?x104 18446744073709551616) ?x104)))
 (and (>= ?x66 (- 9007199254740991)) (<= ?x66 9007199254740991)))))
(assert
 false)
(check-sat)
