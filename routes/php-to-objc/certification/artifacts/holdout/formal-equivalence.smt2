; formal_input_digest: sha256:90d28b55629d62fe81eef0ad444125eea2e94bc6ffa8a3cdb1aacf40e8527d05
; formal-input-sha256: sha256:90d28b55629d62fe81eef0ad444125eea2e94bc6ffa8a3cdb1aacf40e8527d05
; claim-scope: canonical-normalized-source-ir-to-target-relift-ir
; input-domain: profile-total-domain
; original-source-bytes-theorem: false
; formal-input-path: formal-input.json
; independent-source-denotation-sha256: sha256:ee96d38c7aad66a1823c67e1819d6c6f93f617e999eeeefd680098cd1ae7ac2d
; independent-target-denotation-sha256: sha256:4f9b88b79aa5340ae29ed06de88288e849881d3b4e03c5763ca4fe2fcfc7a9d7
; input-alignment: positional-substitution-after-independent-encoding
; benchmark generated from python API
(set-info :status unknown)
(declare-fun target_value () (_ BitVec 64))
(declare-fun source_value () (_ BitVec 64))
(declare-fun target_upper () (_ BitVec 64))
(declare-fun source_upper () (_ BitVec 64))
(assert
 (= source_value target_value))
(assert
 (= source_upper target_upper))
(assert
 false)
(check-sat)
