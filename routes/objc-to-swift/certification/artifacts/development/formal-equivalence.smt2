; formal_input_digest: sha256:46d5389f24619192780ec3fbc2692055bcb4c7e7b41d75fb59e1a93ce357f0eb
; formal-input-sha256: sha256:46d5389f24619192780ec3fbc2692055bcb4c7e7b41d75fb59e1a93ce357f0eb
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
 (let ((?x1028 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x4588 ((_ extract 63 0) ?x1028)))
 (let ((?x2756 (ite (and (distinct ?x1028 ((_ sign_extend 64) ?x4588)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x219 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2044 (ite $x219 0 (ite $x269 ?x79 ?x2756))))
 (let ((?x3753 (ite $x269 ?x79 ?x2044)))
 (= ?x3753 0))))))))))
(assert
 (let ((?x1028 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x4588 ((_ extract 63 0) ?x1028)))
 (let ((?x2756 (ite (and (distinct ?x1028 ((_ sign_extend 64) ?x4588)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x219 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2044 (ite $x219 0 (ite $x269 ?x79 ?x2756))))
 (let ((?x3753 (ite $x269 ?x79 ?x2044)))
 (= ?x3753 0))))))))))
(assert
 false)
(check-sat)
