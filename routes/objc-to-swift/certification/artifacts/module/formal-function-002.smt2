; formal_input_digest: sha256:62a8fb2a2bb4d5c6dfa6c142ce62e68ff267039ac32349a772e1db4df847039b
; formal-input-sha256: sha256:62a8fb2a2bb4d5c6dfa6c142ce62e68ff267039ac32349a772e1db4df847039b
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
 (let (($x2961 (bvsgt source_value source_maximum)))
 (let ((?x4230 (ite $x2961 0 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x41 (bvslt source_value source_minimum)))
 (let ((?x1694 (ite $x41 0 (ite $x4588 ?x209 ?x4230))))
 (let ((?x2883 (ite $x4588 ?x209 ?x1694)))
 (= ?x2883 0)))))))))
(assert
 (let (($x2961 (bvsgt source_value source_maximum)))
 (let ((?x4230 (ite $x2961 0 0)))
 (let ((?x209 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x4588 (and (distinct ?x209 0) true)))
 (let (($x41 (bvslt source_value source_minimum)))
 (let ((?x1694 (ite $x41 0 (ite $x4588 ?x209 ?x4230))))
 (let ((?x2883 (ite $x4588 ?x209 ?x1694)))
 (= ?x2883 0)))))))))
(assert
 false)
(check-sat)
