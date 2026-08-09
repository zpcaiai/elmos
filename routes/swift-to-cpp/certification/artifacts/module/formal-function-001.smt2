; formal_input_digest: sha256:53626537aac2d39770ff9597be809031d7e1ccc2c52a5da96108b44f9cc13062
; formal-input-sha256: sha256:53626537aac2d39770ff9597be809031d7e1ccc2c52a5da96108b44f9cc13062
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
 (let ((?x2271 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x179 ((_ extract 63 0) ?x2271)))
 (let ((?x178 (ite (and (distinct ?x2271 ((_ sign_extend 64) ?x179)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x54 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x1646 (ite $x54 0 (ite $x269 ?x79 ?x178))))
 (let ((?x352 (ite $x269 ?x79 ?x1646)))
 (= ?x352 0))))))))))
(assert
 (let ((?x2271 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x179 ((_ extract 63 0) ?x2271)))
 (let ((?x178 (ite (and (distinct ?x2271 ((_ sign_extend 64) ?x179)) true) 1 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x54 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x1646 (ite $x54 0 (ite $x269 ?x79 ?x178))))
 (let ((?x352 (ite $x269 ?x79 ?x1646)))
 (= ?x352 0))))))))))
(assert
 false)
(check-sat)
