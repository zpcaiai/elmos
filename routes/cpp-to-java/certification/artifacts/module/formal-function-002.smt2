; formal_input_digest: sha256:2656a08540703ae8f359d74e33cf7e4c82f101de6d1583dfbdb415e014f5c3de
; formal-input-sha256: sha256:2656a08540703ae8f359d74e33cf7e4c82f101de6d1583dfbdb415e014f5c3de
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: canonical-finite-no-error-input-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-function-002-input.json
; independent-source-denotation-sha256: sha256:2a9f5f06e16464ef3df8aa26bdaa21bccd3d4930f9a645385368958438970911
; independent-target-denotation-sha256: sha256:9af6e661977c24f50a3c4aa7de8d79d4466d938100225181f18126987b0bba78
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ BitVec 64))
(declare-fun source_value () (_ BitVec 64))
(declare-fun target_minimum () (_ BitVec 64))
(declare-fun source_minimum () (_ BitVec 64))
(declare-fun target_maximum () (_ BitVec 64))
(declare-fun source_maximum () (_ BitVec 64))
(assert
 (= source_value target_value))
(assert
 (= source_minimum target_minimum))
(assert
 (= source_maximum target_maximum))
(assert
 (let (($x3383 (bvsgt source_value source_maximum)))
 (let ((?x1126 (ite $x3383 0 0)))
 (let ((?x4989 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x3419 (and (distinct ?x4989 0) true)))
 (let (($x1111 (bvslt source_value source_minimum)))
 (let ((?x269 (ite $x1111 0 (ite $x3419 ?x4989 ?x1126))))
 (let ((?x4500 (ite $x3419 ?x4989 ?x269)))
 (= ?x4500 0)))))))))
(assert
 (let (($x3383 (bvsgt source_value source_maximum)))
 (let ((?x1126 (ite $x3383 0 0)))
 (let ((?x4989 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x3419 (and (distinct ?x4989 0) true)))
 (let (($x1111 (bvslt source_value source_minimum)))
 (let ((?x269 (ite $x1111 0 (ite $x3419 ?x4989 ?x1126))))
 (let ((?x4500 (ite $x3419 ?x4989 ?x269)))
 (= ?x4500 0)))))))))
(assert
 false)
(check-sat)
