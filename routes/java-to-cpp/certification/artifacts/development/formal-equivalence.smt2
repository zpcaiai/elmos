; formal_input_digest: sha256:137daa02a0f7cd5c60f418de6ea3c1480faba6bcb922f8c701aae3c719842c33
; formal-input-sha256: sha256:137daa02a0f7cd5c60f418de6ea3c1480faba6bcb922f8c701aae3c719842c33
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
 (let ((?x4872 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x56 ((_ extract 63 0) ?x4872)))
 (let ((?x4712 (ite (and (distinct ?x4872 ((_ sign_extend 64) ?x56)) true) 1 0)))
 (let ((?x4989 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x3419 (and (distinct ?x4989 0) true)))
 (let (($x2805 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x4650 (ite $x2805 0 (ite $x3419 ?x4989 ?x4712))))
 (let ((?x888 (ite $x3419 ?x4989 ?x4650)))
 (= ?x888 0))))))))))
(assert
 (let ((?x4872 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x56 ((_ extract 63 0) ?x4872)))
 (let ((?x4712 (ite (and (distinct ?x4872 ((_ sign_extend 64) ?x56)) true) 1 0)))
 (let ((?x4989 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x3419 (and (distinct ?x4989 0) true)))
 (let (($x2805 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x4650 (ite $x2805 0 (ite $x3419 ?x4989 ?x4712))))
 (let ((?x888 (ite $x3419 ?x4989 ?x4650)))
 (= ?x888 0))))))))))
(assert
 false)
(check-sat)
