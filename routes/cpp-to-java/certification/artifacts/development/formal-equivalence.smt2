; formal_input_digest: sha256:7db34747137aad91863d89cf8316a1c42fa109d9680026210119489c7ce7422e
; formal-input-sha256: sha256:7db34747137aad91863d89cf8316a1c42fa109d9680026210119489c7ce7422e
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
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
 (let ((?x15 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x16 ((_ extract 63 0) ?x15)))
 (let ((?x20 (ite (and (distinct ?x15 ((_ sign_extend 64) ?x16)) true) 1 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x21 (and (distinct ?x12 0) true)))
 (let (($x23 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x28 (ite $x23 0 (ite $x21 ?x12 ?x20))))
 (let ((?x34 (ite $x21 ?x12 ?x28)))
 (= ?x34 0))))))))))
(assert
 (let ((?x15 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x16 ((_ extract 63 0) ?x15)))
 (let ((?x20 (ite (and (distinct ?x15 ((_ sign_extend 64) ?x16)) true) 1 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x21 (and (distinct ?x12 0) true)))
 (let (($x23 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x28 (ite $x23 0 (ite $x21 ?x12 ?x20))))
 (let ((?x34 (ite $x21 ?x12 ?x28)))
 (= ?x34 0))))))))))
(assert
 false)
(check-sat)
