; formal_input_digest: sha256:c2c63b461606bb122dd4c3d32ba0aed7f7df2b164fb7aabc4c5ab0854ccd9e4c
; formal-input-sha256: sha256:c2c63b461606bb122dd4c3d32ba0aed7f7df2b164fb7aabc4c5ab0854ccd9e4c
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
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
 (let ((?x101 (ubv_to_int source_value)))
 (let ((?x2653 (ite (bvslt source_value (_ bv0 64)) (- ?x101 18446744073709551616) ?x101)))
 (and (>= ?x2653 (- 9007199254740991)) (<= ?x2653 9007199254740991)))))
(assert
 (let ((?x20 (ubv_to_int source_upper)))
 (let ((?x163 (ite (bvslt source_upper (_ bv0 64)) (- ?x20 18446744073709551616) ?x20)))
 (and (>= ?x163 (- 9007199254740991)) (<= ?x163 9007199254740991)))))
(assert
 (let (($x142 (bvsgt (_ bv0 64) source_value)))
 (let ((?x140 (ite $x142 0 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x137 (bvsgt source_value source_upper)))
 (let ((?x156 (ite $x137 0 (ite $x38 ?x29 ?x140))))
 (let ((?x130 (ite $x38 ?x29 ?x156)))
 (= ?x130 0)))))))))
(assert
 (let (($x142 (bvsgt (_ bv0 64) source_value)))
 (let ((?x140 (ite $x142 0 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x137 (bvsgt source_value source_upper)))
 (let ((?x156 (ite $x137 0 (ite $x38 ?x29 ?x140))))
 (let ((?x130 (ite $x38 ?x29 ?x156)))
 (= ?x130 0)))))))))
(assert
 false)
(check-sat)
