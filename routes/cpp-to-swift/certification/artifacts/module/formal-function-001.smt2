; formal_input_digest: sha256:dc98ae1c8e6fa4cc276c96a6a4fe8513415a3b36c467b433659ebaf1c201b991
; formal-input-sha256: sha256:dc98ae1c8e6fa4cc276c96a6a4fe8513415a3b36c467b433659ebaf1c201b991
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-function-001-input.json
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
 (let ((?x834 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x172 ((_ extract 63 0) ?x834)))
 (let ((?x67 (ite (and (distinct ?x834 ((_ sign_extend 64) ?x172)) true) 1 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x9 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x1977 (ite $x9 0 (ite $x1187 ?x178 ?x67))))
 (let ((?x918 (ite $x1187 ?x178 ?x1977)))
 (= ?x918 0))))))))))
(assert
 (let ((?x834 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x172 ((_ extract 63 0) ?x834)))
 (let ((?x67 (ite (and (distinct ?x834 ((_ sign_extend 64) ?x172)) true) 1 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x9 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x1977 (ite $x9 0 (ite $x1187 ?x178 ?x67))))
 (let ((?x918 (ite $x1187 ?x178 ?x1977)))
 (= ?x918 0))))))))))
(assert
 false)
(check-sat)
