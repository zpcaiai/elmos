; formal_input_digest: sha256:5bd72ced1d17d2cdd189c78eb2ab776db1e3857d581c444558f4035043d31e39
; formal-input-sha256: sha256:5bd72ced1d17d2cdd189c78eb2ab776db1e3857d581c444558f4035043d31e39
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
 (let ((?x831 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x548 ((_ extract 63 0) ?x831)))
 (let ((?x209 (ite (and (distinct ?x831 ((_ sign_extend 64) ?x548)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x2044 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x4730 (ite $x2044 0 (ite $x680 ?x41 ?x209))))
 (let ((?x433 (ite $x680 ?x41 ?x4730)))
 (= ?x433 0))))))))))
(assert
 (let ((?x831 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x548 ((_ extract 63 0) ?x831)))
 (let ((?x209 (ite (and (distinct ?x831 ((_ sign_extend 64) ?x548)) true) 1 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x2044 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x4730 (ite $x2044 0 (ite $x680 ?x41 ?x209))))
 (let ((?x433 (ite $x680 ?x41 ?x4730)))
 (= ?x433 0))))))))))
(assert
 false)
(check-sat)
