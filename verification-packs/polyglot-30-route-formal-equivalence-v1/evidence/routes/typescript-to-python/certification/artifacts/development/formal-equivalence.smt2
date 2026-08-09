; formal_input_digest: sha256:9b3ec907ba084bb5422af878f36628a5a8be764b5035b7846e8254abb6ee1e00
; formal-input-sha256: sha256:9b3ec907ba084bb5422af878f36628a5a8be764b5035b7846e8254abb6ee1e00
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
