; formal_input_digest: sha256:10fb4560d2a9362ba77e927212efc050aeb6a3267c83c9947e6a723a0c1b6828
; formal-input-sha256: sha256:10fb4560d2a9362ba77e927212efc050aeb6a3267c83c9947e6a723a0c1b6828
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
 (let (($x13 (fp.gt source_value source_maximum)))
 (let ((?x32 (ite $x13 0 0)))
 (let ((?x73 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x16 (and (distinct ?x73 0) true)))
 (let (($x28 (fp.lt source_value source_minimum)))
 (let ((?x8 (ite $x28 0 (ite $x16 ?x73 ?x32))))
 (let ((?x158 (ite $x16 ?x73 ?x8)))
 (= ?x158 0)))))))))
(assert
 (let (($x13 (fp.gt source_value source_maximum)))
 (let ((?x32 (ite $x13 0 0)))
 (let ((?x73 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x16 (and (distinct ?x73 0) true)))
 (let (($x28 (fp.lt source_value source_minimum)))
 (let ((?x8 (ite $x28 0 (ite $x16 ?x73 ?x32))))
 (let ((?x158 (ite $x16 ?x73 ?x8)))
 (= ?x158 0)))))))))
(assert
 false)
(check-sat)
