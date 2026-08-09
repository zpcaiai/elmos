; formal_input_digest: sha256:8faf089fd03e034f25a57ec878002c41cbc422fed7d8dc23f5a6425e00888ea6
; formal-input-sha256: sha256:8faf089fd03e034f25a57ec878002c41cbc422fed7d8dc23f5a6425e00888ea6
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:ab2e030ba7ad14d6d3626688dfc132f4a7a7e1d19c321b036b6d0107f2a9b679
; independent-target-denotation-sha256: sha256:290c60f59267a4dc3356ae24339a15486f3d02e4a27422f4e4595aff011bb69e
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ FloatingPoint 11 53))
(declare-fun source_value () (_ FloatingPoint 11 53))
(assert
 (= (fp.to_ieee_bv source_value) (fp.to_ieee_bv target_value)))
(assert
 (not (fp.isNaN source_value)))
(assert
 (not (fp.isInfinite source_value)))
(assert
 (not (fp.isNaN target_value)))
(assert
 (not (fp.isInfinite target_value)))
(assert
 (= 0 0))
(assert
 (= 0 0))
(assert
 false)
(check-sat)
