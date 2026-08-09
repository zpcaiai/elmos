; formal_input_digest: sha256:e56ae94b7cf5f6a6040fe76e786eae3dd740903d508430e5de2cd5db84890d1a
; formal-input-sha256: sha256:e56ae94b7cf5f6a6040fe76e786eae3dd740903d508430e5de2cd5db84890d1a
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
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
 (= (fp.to_ieee_bv source_right) (fp.to_ieee_bv target_right)))
(assert
 false)
(check-sat)
