; formal_input_digest: sha256:232bfe606f62429a4adcadcb22d45033223a54cb3beab30c0fe66d3d7b9bc08f
; formal-input-sha256: sha256:232bfe606f62429a4adcadcb22d45033223a54cb3beab30c0fe66d3d7b9bc08f
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
 (let ((?x1987 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x203 ((_ extract 63 0) ?x1987)))
 (let ((?x79 (ite (and (distinct ?x1987 ((_ sign_extend 64) ?x203)) true) 1 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x3921 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2603 (ite $x3921 0 (ite $x4588 ?x209 ?x79))))
 (let ((?x88 (ite $x4588 ?x209 ?x2603)))
 (= ?x88 0))))))))))
(assert
 (let ((?x1987 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x203 ((_ extract 63 0) ?x1987)))
 (let ((?x79 (ite (and (distinct ?x1987 ((_ sign_extend 64) ?x203)) true) 1 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x3921 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2603 (ite $x3921 0 (ite $x4588 ?x209 ?x79))))
 (let ((?x88 (ite $x4588 ?x209 ?x2603)))
 (= ?x88 0))))))))))
(assert
 false)
(check-sat)
