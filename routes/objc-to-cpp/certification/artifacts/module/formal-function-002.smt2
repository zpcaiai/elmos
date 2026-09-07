; formal_input_digest: sha256:ad4471c468685cc8946c3cf2b152511f146374e02d2d9c6be3172eb9b1b7a68f
; formal-input-sha256: sha256:ad4471c468685cc8946c3cf2b152511f146374e02d2d9c6be3172eb9b1b7a68f
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
 (let (($x175 (bvsgt source_value source_maximum)))
 (let ((?x97 (ite $x175 0 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x90 (bvslt source_value source_minimum)))
 (let ((?x11 (ite $x90 0 (ite $x1694 ?x67 ?x97))))
 (let ((?x92 (ite $x1694 ?x67 ?x11)))
 (= ?x92 0)))))))))
(assert
 (let (($x175 (bvsgt source_value source_maximum)))
 (let ((?x97 (ite $x175 0 0)))
 (let ((?x67 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x1694 (and (distinct ?x67 0) true)))
 (let (($x90 (bvslt source_value source_minimum)))
 (let ((?x11 (ite $x90 0 (ite $x1694 ?x67 ?x97))))
 (let ((?x92 (ite $x1694 ?x67 ?x11)))
 (= ?x92 0)))))))))
(assert
 false)
(check-sat)
