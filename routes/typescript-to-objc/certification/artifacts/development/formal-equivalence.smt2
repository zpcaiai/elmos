; formal_input_digest: sha256:6e574067d63281a310c6c5fe1947c2f400e13415e84524ccd4d54ccf59626bff
; formal-input-sha256: sha256:6e574067d63281a310c6c5fe1947c2f400e13415e84524ccd4d54ccf59626bff
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
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
 (not (fp.isNaN source_subtotal)))
(assert
 (not (fp.isInfinite source_subtotal)))
(assert
 (not (fp.isNaN target_subtotal)))
(assert
 (not (fp.isInfinite target_subtotal)))
(assert
 (= (fp.to_ieee_bv source_tax) (fp.to_ieee_bv target_tax)))
(assert
 (not (fp.isNaN source_tax)))
(assert
 (not (fp.isInfinite source_tax)))
(assert
 (not (fp.isNaN target_tax)))
(assert
 (not (fp.isInfinite target_tax)))
(assert
 (let ((?x14 (fp.add roundNearestTiesToEven source_subtotal source_tax)))
 (let (($x20 (not (fp.isInfinite ?x14))))
 (let (($x18 (not (fp.isNaN ?x14))))
 (and $x18 $x20)))))
(assert
 (let ((?x14 (fp.add roundNearestTiesToEven source_subtotal source_tax)))
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x25 (fp.lt source_subtotal ?x24)))
 (let ((?x35 (ite $x25 ?x24 ?x14)))
 (and (not (fp.isNaN ?x35)) (not (fp.isInfinite ?x35))))))))
(assert
 (let ((?x16 (ite false 2 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let ((?x23 (ite $x22 ?x12 ?x16)))
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x25 (fp.lt source_subtotal ?x24)))
 (let ((?x29 (ite $x25 0 ?x23)))
 (let ((?x36 (ite $x22 ?x12 ?x29)))
 (= ?x36 0))))))))))
(assert
 (let ((?x16 (ite false 2 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let ((?x23 (ite $x22 ?x12 ?x16)))
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x25 (fp.lt source_subtotal ?x24)))
 (let ((?x29 (ite $x25 0 ?x23)))
 (let ((?x36 (ite $x22 ?x12 ?x29)))
 (= ?x36 0))))))))))
(assert
 false)
(check-sat)
