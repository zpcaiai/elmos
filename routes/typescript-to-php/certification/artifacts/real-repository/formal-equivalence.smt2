; formal_input_digest: sha256:b694ec47a3c23025240220e5adfe776203138a875f381362bf1f946877aafcb3
; formal-input-sha256: sha256:b694ec47a3c23025240220e5adfe776203138a875f381362bf1f946877aafcb3
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: nodejs-es2022-esm-safe-integer-finite-v1
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:0e8045d0a7f6aeccde103f13e67b70754805cdb027e68a06be5e0c2649d92281
; independent-target-denotation-sha256: sha256:3eac2299c09ddeb7125c03fcbefd34d07b4a6f37e5b20cacbcc410b8f2dd0b79
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_left () (_ FloatingPoint 11 53))
(declare-fun source_left () (_ FloatingPoint 11 53))
(declare-fun target_right () (_ FloatingPoint 11 53))
(declare-fun source_right () (_ FloatingPoint 11 53))
(assert
 (= (fp.to_ieee_bv source_left) (fp.to_ieee_bv target_left)))
(assert
 (not (fp.isNaN source_left)))
(assert
 (not (fp.isInfinite source_left)))
(assert
 (not (fp.isNaN target_left)))
(assert
 (not (fp.isInfinite target_left)))
(assert
 (= (fp.to_ieee_bv source_right) (fp.to_ieee_bv target_right)))
(assert
 (not (fp.isNaN source_right)))
(assert
 (not (fp.isInfinite source_right)))
(assert
 (not (fp.isNaN target_right)))
(assert
 (not (fp.isInfinite target_right)))
(assert
 (let ((?x69 (fp.sub roundNearestTiesToEven source_left source_right)))
 (and (not (fp.isNaN ?x69)) (not (fp.isInfinite ?x69)))))
(assert
 (let ((?x69 (fp.sub roundNearestTiesToEven source_left source_right)))
 (let ((?x24 ((_ to_fp 11 53) roundNearestTiesToEven (_ bv0 64))))
 (let (($x8 (fp.lt source_left source_right)))
 (let ((?x36 (ite $x8 ?x24 ?x69)))
 (and (not (fp.isNaN ?x36)) (not (fp.isInfinite ?x36))))))))
(assert
 (let ((?x68 (ite false 2 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let ((?x18 (ite $x22 ?x12 ?x68)))
 (let (($x8 (fp.lt source_left source_right)))
 (let ((?x40 (ite $x8 0 ?x18)))
 (let ((?x29 (ite $x22 ?x12 ?x40)))
 (= ?x29 0)))))))))
(assert
 (let ((?x68 (ite false 2 0)))
 (let ((?x12 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x22 (and (distinct ?x12 0) true)))
 (let ((?x18 (ite $x22 ?x12 ?x68)))
 (let (($x8 (fp.lt source_left source_right)))
 (let ((?x40 (ite $x8 0 ?x18)))
 (let ((?x29 (ite $x22 ?x12 ?x40)))
 (= ?x29 0)))))))))
(assert
 false)
(check-sat)
