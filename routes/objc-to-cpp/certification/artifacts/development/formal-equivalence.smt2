; formal_input_digest: sha256:562a81d8f9f2a4ce6fa6523dfa56b0acb9e3c3d923387907ede55c3fe7649fb0
; formal-input-sha256: sha256:562a81d8f9f2a4ce6fa6523dfa56b0acb9e3c3d923387907ede55c3fe7649fb0
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
 (let ((?x1649 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1694 ((_ extract 63 0) ?x1649)))
 (let ((?x963 (ite (and (distinct ?x1649 ((_ sign_extend 64) ?x1694)) true) 1 0)))
 (let ((?x73 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x16 (and (distinct ?x73 0) true)))
 (let (($x83 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x25 (ite $x83 0 (ite $x16 ?x73 ?x963))))
 (let ((?x179 (ite $x16 ?x73 ?x25)))
 (= ?x179 0))))))))))
(assert
 (let ((?x1649 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1694 ((_ extract 63 0) ?x1649)))
 (let ((?x963 (ite (and (distinct ?x1649 ((_ sign_extend 64) ?x1694)) true) 1 0)))
 (let ((?x73 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x16 (and (distinct ?x73 0) true)))
 (let (($x83 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x25 (ite $x83 0 (ite $x16 ?x73 ?x963))))
 (let ((?x179 (ite $x16 ?x73 ?x25)))
 (= ?x179 0))))))))))
(assert
 false)
(check-sat)
