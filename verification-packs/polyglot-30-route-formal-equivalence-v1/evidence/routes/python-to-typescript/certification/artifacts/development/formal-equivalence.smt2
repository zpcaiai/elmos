; formal_input_digest: sha256:4857a4d9deff287f3754207d56c355ff19b89d8d6c7e1a89c3752bb2bbbd97d5
; formal-input-sha256: sha256:4857a4d9deff287f3754207d56c355ff19b89d8d6c7e1a89c3752bb2bbbd97d5
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
 (let ((?x308 (ubv_to_int source_subtotal)))
 (let ((?x86 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x308 18446744073709551616) ?x308)))
 (and (>= ?x86 (- 9007199254740991)) (<= ?x86 9007199254740991)))))
(assert
 (let ((?x393 (ubv_to_int source_tax)))
 (let ((?x88 (ite (bvslt source_tax (_ bv0 64)) (- ?x393 18446744073709551616) ?x393)))
 (and (>= ?x88 (- 9007199254740991)) (<= ?x88 9007199254740991)))))
(assert
 (let ((?x266 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1435 ((_ extract 63 0) ?x266)))
 (let ((?x26 (ubv_to_int ?x1435)))
 (let ((?x2801 (ite (bvslt ?x1435 (_ bv0 64)) (- ?x26 18446744073709551616) ?x26)))
 (and (>= ?x2801 (- 9007199254740991)) (<= ?x2801 9007199254740991)))))))
(assert
 false)
(check-sat)
