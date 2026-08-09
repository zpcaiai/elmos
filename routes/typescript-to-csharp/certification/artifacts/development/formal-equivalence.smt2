; formal_input_digest: sha256:017abadb94797376242bf472d41d1babca7d9d7279bf5361fe517859f00590c5
; formal-input-sha256: sha256:017abadb94797376242bf472d41d1babca7d9d7279bf5361fe517859f00590c5
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:7a984a8bf8944afce8eee8f3c43cc89bd19843a4abb91a4a58ac1fc7753732bf
; independent-target-denotation-sha256: sha256:f4adc5a0e454f055833f9c2eb8bfccd46ac986c1e4276ea3d6e68cba2c683e6c
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_subtotal () (_ FloatingPoint 11 53))
(declare-fun source_subtotal () (_ FloatingPoint 11 53))
(declare-fun target_tax () (_ FloatingPoint 11 53))
(declare-fun source_tax () (_ FloatingPoint 11 53))
(assert
 (= (fp.to_ieee_bv source_subtotal) (fp.to_ieee_bv target_subtotal)))
(assert
 (= (fp.to_ieee_bv source_tax) (fp.to_ieee_bv target_tax)))
(assert
 false)
(check-sat)
