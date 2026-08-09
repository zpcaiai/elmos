; formal_input_digest: sha256:a94dd3bb3b5cf0ec2ae42c9d47333bd22eaff1680f3b76513e6edab725eaebbb
; formal-input-sha256: sha256:a94dd3bb3b5cf0ec2ae42c9d47333bd22eaff1680f3b76513e6edab725eaebbb
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
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
 (let ((?x107 (ubv_to_int source_subtotal)))
 (let ((?x154 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x107 18446744073709551616) ?x107)))
 (and (>= ?x154 (- 9007199254740991)) (<= ?x154 9007199254740991)))))
(assert
 (let ((?x236 (ubv_to_int source_tax)))
 (let ((?x106 (ite (bvslt source_tax (_ bv0 64)) (- ?x236 18446744073709551616) ?x236)))
 (and (>= ?x106 (- 9007199254740991)) (<= ?x106 9007199254740991)))))
(assert
 (let ((?x234 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1386 ((_ extract 63 0) ?x234)))
 (let ((?x61 (ubv_to_int ?x1386)))
 (let ((?x2829 (ite (bvslt ?x1386 (_ bv0 64)) (- ?x61 18446744073709551616) ?x61)))
 (and (>= ?x2829 (- 9007199254740991)) (<= ?x2829 9007199254740991)))))))
(assert
 false)
(check-sat)
