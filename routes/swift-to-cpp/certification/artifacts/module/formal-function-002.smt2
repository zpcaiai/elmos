; formal_input_digest: sha256:dbd38e0cca63b3a99fc404d13fee99b2b0e6cc53d2c8cc9dbd054cd0c637d310
; formal-input-sha256: sha256:dbd38e0cca63b3a99fc404d13fee99b2b0e6cc53d2c8cc9dbd054cd0c637d310
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
 (let (($x1837 (bvsgt source_value source_maximum)))
 (let ((?x1867 (ite $x1837 0 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x209 (bvslt source_value source_minimum)))
 (let ((?x1538 (ite $x209 0 (ite $x269 ?x79 ?x1867))))
 (let ((?x41 (ite $x269 ?x79 ?x1538)))
 (= ?x41 0)))))))))
(assert
 (let (($x1837 (bvsgt source_value source_maximum)))
 (let ((?x1867 (ite $x1837 0 0)))
 (let ((?x79 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x269 (and (distinct ?x79 0) true)))
 (let (($x209 (bvslt source_value source_minimum)))
 (let ((?x1538 (ite $x209 0 (ite $x269 ?x79 ?x1867))))
 (let ((?x41 (ite $x269 ?x79 ?x1538)))
 (= ?x41 0)))))))))
(assert
 false)
(check-sat)
