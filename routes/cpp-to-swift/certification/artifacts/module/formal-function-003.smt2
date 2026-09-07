; formal_input_digest: sha256:6235499600b650d349da6b2cb3baf5a3f1c1f32d59f5d60811591878b8480a0e
; formal-input-sha256: sha256:6235499600b650d349da6b2cb3baf5a3f1c1f32d59f5d60811591878b8480a0e
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
 (let (($x693 (fp.gt source_value source_maximum)))
 (let ((?x83 (ite $x693 0 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x51 (fp.lt source_value source_minimum)))
 (let ((?x18 (ite $x51 0 (ite $x1187 ?x178 ?x83))))
 (let ((?x1653 (ite $x1187 ?x178 ?x18)))
 (= ?x1653 0)))))))))
(assert
 (let (($x693 (fp.gt source_value source_maximum)))
 (let ((?x83 (ite $x693 0 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x51 (fp.lt source_value source_minimum)))
 (let ((?x18 (ite $x51 0 (ite $x1187 ?x178 ?x83))))
 (let ((?x1653 (ite $x1187 ?x178 ?x18)))
 (= ?x1653 0)))))))))
(assert
 false)
(check-sat)
