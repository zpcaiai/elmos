; formal_input_digest: sha256:bebc56b2f665c3eeafcf62f4aac41a59cd87f6f27fe6dd4da0543d669eb6988d
; formal-input-sha256: sha256:bebc56b2f665c3eeafcf62f4aac41a59cd87f6f27fe6dd4da0543d669eb6988d
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: profile-total-domain
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
 false)
(check-sat)
