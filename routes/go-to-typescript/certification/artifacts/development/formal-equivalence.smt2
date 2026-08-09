; formal_input_digest: sha256:a92f1c625d5ddee39e39d5753250946d444343e7ba62cf05fa9f2dd8d3906290
; formal-input-sha256: sha256:a92f1c625d5ddee39e39d5753250946d444343e7ba62cf05fa9f2dd8d3906290
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
 (let ((?x9 (ubv_to_int source_subtotal)))
 (let ((?x129 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x9 18446744073709551616) ?x9)))
 (and (>= ?x129 (- 9007199254740991)) (<= ?x129 9007199254740991)))))
(assert
 (let ((?x309 (ubv_to_int source_tax)))
 (let ((?x188 (ite (bvslt source_tax (_ bv0 64)) (- ?x309 18446744073709551616) ?x309)))
 (and (>= ?x188 (- 9007199254740991)) (<= ?x188 9007199254740991)))))
(assert
 (let ((?x385 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1655 ((_ extract 63 0) ?x385)))
 (let ((?x228 (ubv_to_int ?x1655)))
 (let ((?x415 (ite (bvslt ?x1655 (_ bv0 64)) (- ?x228 18446744073709551616) ?x228)))
 (and (>= ?x415 (- 9007199254740991)) (<= ?x415 9007199254740991)))))))
(assert
 false)
(check-sat)
