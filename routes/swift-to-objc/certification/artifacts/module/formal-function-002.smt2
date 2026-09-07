; formal_input_digest: sha256:56d651704fd998ca39f3d7f7e4b727edc52355d0232d3e2f0480217e035724d0
; formal-input-sha256: sha256:56d651704fd998ca39f3d7f7e4b727edc52355d0232d3e2f0480217e035724d0
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
