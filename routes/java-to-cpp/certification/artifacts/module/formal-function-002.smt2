; formal_input_digest: sha256:e91b831cef6ffc318524bf2d8107b588b8a691be368e30e25b454eb4cabfbf47
; formal-input-sha256: sha256:e91b831cef6ffc318524bf2d8107b588b8a691be368e30e25b454eb4cabfbf47
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
 (let (($x3766 (bvsgt source_value source_maximum)))
 (let ((?x2776 (ite $x3766 0 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let (($x4755 (bvslt source_value source_minimum)))
 (let ((?x4250 (ite $x4755 0 (ite $x56 ?x3383 ?x2776))))
 (let ((?x3096 (ite $x56 ?x3383 ?x4250)))
 (= ?x3096 0)))))))))
(assert
 (let (($x3766 (bvsgt source_value source_maximum)))
 (let ((?x2776 (ite $x3766 0 0)))
 (let ((?x3383 (ite (and (distinct 0 0) true) 0 0)))
 (let (($x56 (and (distinct ?x3383 0) true)))
 (let (($x4755 (bvslt source_value source_minimum)))
 (let ((?x4250 (ite $x4755 0 (ite $x56 ?x3383 ?x2776))))
 (let ((?x3096 (ite $x56 ?x3383 ?x4250)))
 (= ?x3096 0)))))))))
(assert
 false)
(check-sat)
