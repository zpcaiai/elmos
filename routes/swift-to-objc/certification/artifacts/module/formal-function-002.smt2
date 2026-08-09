; formal_input_digest: sha256:f30cb931f08b1c77b16419da34a582b97c4c6e9b8fb926afb6c76a5cd98922c5
; formal-input-sha256: sha256:f30cb931f08b1c77b16419da34a582b97c4c6e9b8fb926afb6c76a5cd98922c5
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
 (let (($x4989 (bvsgt source_value source_maximum)))
 (let ((?x2963 (ite $x4989 0 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x4570 (bvslt source_value source_minimum)))
 (let ((?x77 (ite $x4570 0 (ite $x680 ?x41 ?x2963))))
 (let ((?x1413 (ite $x680 ?x41 ?x77)))
 (= ?x1413 0)))))))))
(assert
 (let (($x4989 (bvsgt source_value source_maximum)))
 (let ((?x2963 (ite $x4989 0 0)))
 (let ((?x41 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x680 (and (distinct ?x41 0) true)))
 (let (($x4570 (bvslt source_value source_minimum)))
 (let ((?x77 (ite $x4570 0 (ite $x680 ?x41 ?x2963))))
 (let ((?x1413 (ite $x680 ?x41 ?x77)))
 (= ?x1413 0)))))))))
(assert
 false)
(check-sat)
