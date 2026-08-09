; formal_input_digest: sha256:7e226f0a87e9984efe96919ba4209c625955a1d7d504b047f56b20ae811df872
; formal-input-sha256: sha256:7e226f0a87e9984efe96919ba4209c625955a1d7d504b047f56b20ae811df872
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
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
 (let ((?x399 (ubv_to_int source_subtotal)))
 (let ((?x1135 (ite (bvslt source_subtotal (_ bv0 64)) (- ?x399 18446744073709551616) ?x399)))
 (and (>= ?x1135 (- 9007199254740991)) (<= ?x1135 9007199254740991)))))
(assert
 (let ((?x461 (ubv_to_int source_tax)))
 (let ((?x185 (ite (bvslt source_tax (_ bv0 64)) (- ?x461 18446744073709551616) ?x461)))
 (and (>= ?x185 (- 9007199254740991)) (<= ?x185 9007199254740991)))))
(assert
 (let ((?x248 (bvadd ((_ sign_extend 64) source_subtotal) ((_ sign_extend 64) source_tax))))
 (let ((?x1715 ((_ extract 63 0) ?x248)))
 (let ((?x265 (ubv_to_int ?x1715)))
 (let ((?x206 (ite (bvslt ?x1715 (_ bv0 64)) (- ?x265 18446744073709551616) ?x265)))
 (and (>= ?x206 (- 9007199254740991)) (<= ?x206 9007199254740991)))))))
(assert
 false)
(check-sat)
