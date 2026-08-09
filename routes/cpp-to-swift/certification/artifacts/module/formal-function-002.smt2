; formal_input_digest: sha256:5b93beb1badeee8911c87fa40053c8ad5c66a8b8f2d940de0c1908dba6d3ca91
; formal-input-sha256: sha256:5b93beb1badeee8911c87fa40053c8ad5c66a8b8f2d940de0c1908dba6d3ca91
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
 (let (($x5222 (bvsgt source_value source_maximum)))
 (let ((?x4537 (ite $x5222 0 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x5171 (bvslt source_value source_minimum)))
 (let ((?x21 (ite $x5171 0 (ite $x1187 ?x178 ?x4537))))
 (let ((?x5217 (ite $x1187 ?x178 ?x21)))
 (= ?x5217 0)))))))))
(assert
 (let (($x5222 (bvsgt source_value source_maximum)))
 (let ((?x4537 (ite $x5222 0 0)))
 (let ((?x178 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1187 (and (distinct ?x178 0) true)))
 (let (($x5171 (bvslt source_value source_minimum)))
 (let ((?x21 (ite $x5171 0 (ite $x1187 ?x178 ?x4537))))
 (let ((?x5217 (ite $x1187 ?x178 ?x21)))
 (= ?x5217 0)))))))))
(assert
 false)
(check-sat)
