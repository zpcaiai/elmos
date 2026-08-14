; formal_input_digest: sha256:630300c20fd838c1aec106f0d3d53496a56608cc4012880c5932cd1e24f0ee66
; formal-input-sha256: sha256:630300c20fd838c1aec106f0d3d53496a56608cc4012880c5932cd1e24f0ee66
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
 (let ((?x390 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1538 ((_ extract 63 0) ?x390)))
 (let ((?x4989 (ite (and (distinct ?x390 ((_ sign_extend 64) ?x1538)) true) 1 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let (($x3524 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x53 (ite $x3524 0 (ite $x56 ?x3383 ?x4989))))
 (let ((?x831 (ite $x56 ?x3383 ?x53)))
 (= ?x831 0))))))))))
(assert
 (let ((?x390 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1538 ((_ extract 63 0) ?x390)))
 (let ((?x4989 (ite (and (distinct ?x390 ((_ sign_extend 64) ?x1538)) true) 1 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let (($x3524 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x53 (ite $x3524 0 (ite $x56 ?x3383 ?x4989))))
 (let ((?x831 (ite $x56 ?x3383 ?x53)))
 (= ?x831 0))))))))))
(assert
 false)
(check-sat)
