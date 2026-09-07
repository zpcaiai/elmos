; formal_input_digest: sha256:ac1a15808d900820b605c8382d4f6fefbb6df19e014f7cbcf467ad8061981bd7
; formal-input-sha256: sha256:ac1a15808d900820b605c8382d4f6fefbb6df19e014f7cbcf467ad8061981bd7
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
 (let ((?x1122 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x269 ((_ extract 63 0) ?x1122)))
 (let ((?x25 (ite (and (distinct ?x1122 ((_ sign_extend 64) ?x269)) true) 1 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x5022 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2014 (ite $x5022 0 (ite $x1187 ?x178 ?x25))))
 (let ((?x763 (ite $x1187 ?x178 ?x2014)))
 (= ?x763 0))))))))))
(assert
 (let ((?x1122 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x269 ((_ extract 63 0) ?x1122)))
 (let ((?x25 (ite (and (distinct ?x1122 ((_ sign_extend 64) ?x269)) true) 1 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x5022 (bvsgt (_ bv0 64) source_subtotal)))
 (let ((?x2014 (ite $x5022 0 (ite $x1187 ?x178 ?x25))))
 (let ((?x763 (ite $x1187 ?x178 ?x2014)))
 (= ?x763 0))))))))))
(assert
 false)
(check-sat)
