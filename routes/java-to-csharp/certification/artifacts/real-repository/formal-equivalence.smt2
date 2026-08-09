; formal_input_digest: sha256:f4b9f165f1257ab16365a6dcd5f7b9784c26f974b2e0d9f85ca2b42d16b71626
; formal-input-sha256: sha256:f4b9f165f1257ab16365a6dcd5f7b9784c26f974b2e0d9f85ca2b42d16b71626
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:56f9cc8a3f5018f5eb370c9a59544aeacca1ad4e3b917f18f75d312198d73925
; independent-target-denotation-sha256: sha256:6af246fb419b79cc485f28bb4872eaa7f8db4900d12cc464b79c55cc0a15a09c
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_left () (_ BitVec 64))
(declare-fun source_left () (_ BitVec 64))
(declare-fun target_right () (_ BitVec 64))
(declare-fun source_right () (_ BitVec 64))
(assert
 (= source_left target_left))
(assert
 (= source_right target_right))
(assert
 false)
(check-sat)
