; formal_input_digest: sha256:151a545acb5be8ac5c43bd606bb1e55e1ac8382e456c71be37acf4677776998f
; formal-input-sha256: sha256:151a545acb5be8ac5c43bd606bb1e55e1ac8382e456c71be37acf4677776998f
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:0ea3506a291ba9e34d6410fcee148d1fe945c5f185c3064e0b6f71d36816be78
; independent-target-denotation-sha256: sha256:a879f5b08557c731377ea94c19343f94cedf7500936fd58e5aeb051fd691e995
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_subtotal () (_ BitVec 64))
(declare-fun source_subtotal () (_ BitVec 64))
(declare-fun target_tax () (_ BitVec 64))
(declare-fun source_tax () (_ BitVec 64))
(assert
 (= source_subtotal target_subtotal))
(assert
 (= source_tax target_tax))
(assert
 (let ((?x75 (ubv_to_int source_subtotal)))
 (let ((?x78 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x75 18446744073709551616) ?x75)))
 (and (>= ?x78 (- 9007199254740991)) (<= ?x78 9007199254740991)))))
(assert
 (let ((?x82 (ubv_to_int source_tax)))
 (let ((?x85 (ite (bvslt source_tax (_ bv0 64)) (- ?x82 18446744073709551616) ?x82)))
 (and (>= ?x85 (- 9007199254740991)) (<= ?x85 9007199254740991)))))
(assert
 (let ((?x32 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x33 ((_ extract 63 0) ?x32)))
 (let ((?x89 (ubv_to_int ?x33)))
 (let ((?x92 (ite (bvslt ?x33 (_ bv0 64)) (- ?x89 18446744073709551616) ?x89)))
 (and (>= ?x92 (- 9007199254740991)) (<= ?x92 9007199254740991)))))))
(assert
 (let ((?x32 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x33 ((_ extract 63 0) ?x32)))
 (let ((?x37 (ite (and (distinct ?x32 ((_ sign_extend 64) ?x33)) true) 1 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x40 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x45 (ite $x40 0 (ite $x38 ?x29 ?x37))))
 (let ((?x51 (ite $x38 ?x29 ?x45)))
 (= ?x51 0))))))))))
(assert
 (let ((?x32 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x33 ((_ extract 63 0) ?x32)))
 (let ((?x37 (ite (and (distinct ?x32 ((_ sign_extend 64) ?x33)) true) 1 0)))
 (let ((?x29 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x38 (and (distinct ?x29 0) true)))
 (let (($x40 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x45 (ite $x40 0 (ite $x38 ?x29 ?x37))))
 (let ((?x51 (ite $x38 ?x29 ?x45)))
 (= ?x51 0))))))))))
(assert
 false)
(check-sat)
