; formal_input_digest: sha256:a92cb2a77082d382b954360f6ee8421d371aa0b4dded90e809d2eabef649b50e
; formal-input-sha256: sha256:a92cb2a77082d382b954360f6ee8421d371aa0b4dded90e809d2eabef649b50e
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
 (let ((?x91 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x63 ((_ extract 63 0) ?x91)))
 (let ((?x73 (ite (and (distinct ?x91 ((_ sign_extend 64) ?x63)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x28 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x5168 (ite $x28 0 (ite $x1694 ?x67 ?x73))))
 (let ((?x105 (ite $x1694 ?x67 ?x5168)))
 (= ?x105 0))))))))))
(assert
 (let ((?x91 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x63 ((_ extract 63 0) ?x91)))
 (let ((?x73 (ite (and (distinct ?x91 ((_ sign_extend 64) ?x63)) true) 1 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x28 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x5168 (ite $x28 0 (ite $x1694 ?x67 ?x73))))
 (let ((?x105 (ite $x1694 ?x67 ?x5168)))
 (= ?x105 0))))))))))
(assert
 false)
(check-sat)
