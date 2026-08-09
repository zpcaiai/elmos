; formal_input_digest: sha256:6c27a2254c8f273983e3bbc4321bc9a43d478d17ce302d29067a3d77e7e29554
; formal-input-sha256: sha256:6c27a2254c8f273983e3bbc4321bc9a43d478d17ce302d29067a3d77e7e29554
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
 (let ((?x4635 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x3419 ((_ extract 63 0) ?x4635)))
 (let ((?x3614 (ite (and (distinct ?x4635 ((_ sign_extend 64) ?x3419)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x4699 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x5181 (ite $x4699 0 (ite $x680 ?x41 ?x3614))))
 (let ((?x5129 (ite $x680 ?x41 ?x5181)))
 (= ?x5129 0))))))))))
(assert
 (let ((?x4635 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x3419 ((_ extract 63 0) ?x4635)))
 (let ((?x3614 (ite (and (distinct ?x4635 ((_ sign_extend 64) ?x3419)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x4699 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x5181 (ite $x4699 0 (ite $x680 ?x41 ?x3614))))
 (let ((?x5129 (ite $x680 ?x41 ?x5181)))
 (= ?x5129 0))))))))))
(assert
 false)
(check-sat)
