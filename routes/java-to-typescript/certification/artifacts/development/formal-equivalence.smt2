; formal_input_digest: sha256:68d632fdf434b2af38c024ee9c01072ca05fcda69484d0d7fe16b70c982286a6
; formal-input-sha256: sha256:68d632fdf434b2af38c024ee9c01072ca05fcda69484d0d7fe16b70c982286a6
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
 (let ((?x66 (ubv_to_int source_subtotal)))
 (let ((?x85 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x66 18446744073709551616) ?x66)))
 (and (>= ?x85 (- 9007199254740991)) (<= ?x85 9007199254740991)))))
(assert
 (let ((?x23 (ubv_to_int source_tax)))
 (let ((?x71 (ite (bvslt source_tax (_ bv0 64)) (- ?x23 18446744073709551616) ?x23)))
 (and (>= ?x71 (- 9007199254740991)) (<= ?x71 9007199254740991)))))
(assert
 (let ((?x36 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x13 ((_ extract 63 0) ?x36)))
 (let ((?x95 (ubv_to_int ?x13)))
 (let ((?x98 (ite (bvslt ?x13 (_ bv0 64)) (- ?x95 18446744073709551616) ?x95)))
 (and (>= ?x98 (- 9007199254740991)) (<= ?x98 9007199254740991)))))))
(assert
 false)
(check-sat)
