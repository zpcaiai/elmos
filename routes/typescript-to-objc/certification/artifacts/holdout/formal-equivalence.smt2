; formal_input_digest: sha256:e161baf755a5d59f43c030aa14641c5d1c7af219823e1f009c32af8072a77fa9
; formal-input-sha256: sha256:e161baf755a5d59f43c030aa14641c5d1c7af219823e1f009c32af8072a77fa9
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
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
 (not (fp.isNaN source_value)))
(assert
 (not (fp.isInfinite source_value)))
(assert
 (not (fp.isNaN target_value)))
(assert
 (not (fp.isInfinite target_value)))
(assert
 (= (fp.to_ieee_bv source_upper) (fp.to_ieee_bv target_upper)))
(assert
 (not (fp.isNaN source_upper)))
(assert
 (not (fp.isInfinite source_upper)))
(assert
 (not (fp.isNaN target_upper)))
(assert
 (not (fp.isInfinite target_upper)))
(assert
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x94 (fp.lt source_value ?x24)))
 (let (($x80 (fp.gt source_value source_upper)))
 (let ((?x223 (ite $x80 source_upper (ite $x94 ?x24 source_value))))
 (and (not (fp.isNaN ?x223)) (not (fp.isInfinite ?x223))))))))
(assert
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x94 (fp.lt source_value ?x24)))
 (let ((?x82 (ite $x94 0 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let (($x80 (fp.gt source_value source_upper)))
 (let ((?x77 (ite $x80 0 (ite $x22 ?x12 ?x82))))
 (let ((?x229 (ite $x22 ?x12 ?x77)))
 (= ?x229 0))))))))))
(assert
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x94 (fp.lt source_value ?x24)))
 (let ((?x82 (ite $x94 0 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let (($x80 (fp.gt source_value source_upper)))
 (let ((?x77 (ite $x80 0 (ite $x22 ?x12 ?x82))))
 (let ((?x229 (ite $x22 ?x12 ?x77)))
 (= ?x229 0))))))))))
(assert
 false)
(check-sat)
