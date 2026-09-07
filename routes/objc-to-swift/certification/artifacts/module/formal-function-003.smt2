; formal_input_digest: sha256:aa7785d32ee81beeea4b1107ffd4c5f7f1b7a176a26d031fc0068e4d10c004a6
; formal-input-sha256: sha256:aa7785d32ee81beeea4b1107ffd4c5f7f1b7a176a26d031fc0068e4d10c004a6
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-function-003-input.json
; independent-source-denotation-sha256: sha256:d11ca1a62c16815bca6c75cddb722cb973d11f45830d1513b759a723450808f8
; independent-target-denotation-sha256: sha256:5f73b860c5bbc8d7cfeb756c04959d5059687d24f2e26d5a9912876dfa916a25
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ FloatingPoint 11 53))
(declare-fun source_value () (_ FloatingPoint 11 53))
(declare-fun target_minimum () (_ FloatingPoint 11 53))
(declare-fun source_minimum () (_ FloatingPoint 11 53))
(declare-fun target_maximum () (_ FloatingPoint 11 53))
(declare-fun source_maximum () (_ FloatingPoint 11 53))
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
 (= (fp.to_ieee_bv source_minimum) (fp.to_ieee_bv target_minimum)))
(assert
 (not (fp.isNaN source_minimum)))
(assert
 (not (fp.isInfinite source_minimum)))
(assert
 (not (fp.isNaN target_minimum)))
(assert
 (not (fp.isInfinite target_minimum)))
(assert
 (= (fp.to_ieee_bv source_maximum) (fp.to_ieee_bv target_maximum)))
(assert
 (not (fp.isNaN source_maximum)))
(assert
 (not (fp.isInfinite source_maximum)))
(assert
 (not (fp.isNaN target_maximum)))
(assert
 (not (fp.isInfinite target_maximum)))
(assert
 (let (($x4972 (fp.gt source_value source_maximum)))
 (let ((?x5022 (ite $x4972 0 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x2044 (fp.lt source_value source_minimum)))
 (let ((?x3430 (ite $x2044 0 (ite $x4588 ?x209 ?x5022))))
 (let ((?x4542 (ite $x4588 ?x209 ?x3430)))
 (= ?x4542 0)))))))))
(assert
 (let (($x4972 (fp.gt source_value source_maximum)))
 (let ((?x5022 (ite $x4972 0 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x2044 (fp.lt source_value source_minimum)))
 (let ((?x3430 (ite $x2044 0 (ite $x4588 ?x209 ?x5022))))
 (let ((?x4542 (ite $x4588 ?x209 ?x3430)))
 (= ?x4542 0)))))))))
(assert
 false)
(check-sat)
