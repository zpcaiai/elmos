; formal_input_digest: sha256:418c7ff1d6c22919c9f4cf22572077c13295f0449758e839bb3ae334dbf3925c
; formal-input-sha256: sha256:418c7ff1d6c22919c9f4cf22572077c13295f0449758e839bb3ae334dbf3925c
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
 (let ((?x1300 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1187 ((_ extract 63 0) ?x1300)))
 (let ((?x4211 (ite (and (distinct ?x1300 ((_ sign_extend 64) ?x1187)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x606 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x51 (ite $x606 0 (ite $x1694 ?x67 ?x4211))))
 (let ((?x164 (ite $x1694 ?x67 ?x51)))
 (= ?x164 0))))))))))
(assert
 (let ((?x1300 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1187 ((_ extract 63 0) ?x1300)))
 (let ((?x4211 (ite (and (distinct ?x1300 ((_ sign_extend 64) ?x1187)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x606 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x51 (ite $x606 0 (ite $x1694 ?x67 ?x4211))))
 (let ((?x164 (ite $x1694 ?x67 ?x51)))
 (= ?x164 0))))))))))
(assert
 false)
(check-sat)
