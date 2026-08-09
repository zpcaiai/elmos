; formal_input_digest: sha256:7ede1aa9a053b0d7628690c496df8610755fe7011768b5f9c2ab08384629c61b
; formal-input-sha256: sha256:7ede1aa9a053b0d7628690c496df8610755fe7011768b5f9c2ab08384629c61b
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:1fc26fd02270a373a9f7b1bd5b9422d584509e865824208b0e4f214f1a14b8b8
; independent-target-denotation-sha256: sha256:c2c888387ad580463d112d609ae451a5faae4cb8a37badae15abe6b8652e3a29
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ FloatingPoint 11 53))
(declare-fun source_value () (_ FloatingPoint 11 53))
(declare-fun target_upper () (_ FloatingPoint 11 53))
(declare-fun source_upper () (_ FloatingPoint 11 53))
(assert
 (= (fp.to_ieee_bv source_value) (fp.to_ieee_bv target_value)))
(assert
 (= (fp.to_ieee_bv source_upper) (fp.to_ieee_bv target_upper)))
(assert
 false)
(check-sat)
