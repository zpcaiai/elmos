---
name: edi-as2-mft-b2b-partner-modernizer
description: Modernize EDI, AS2, SFTP, MFT, trading-partner agreements, certificates, mappings, acknowledgements, and B2B operations. Use for partner onboarding, document migration, certificate rotation, file delivery, or partner-by-partner cutover.
---

# EDI, AS2, MFT, and B2B Modernization

## Model the partner agreement

Record partner organization, contacts, environments, protocol, endpoint, certificates, documents, mappings, schedule, SLA, support, and versioned agreement. Support AS2, SFTP, FTPS, HTTPS, OFTP, VAN, email, and custom transport; support X12, EDIFACT, XML, JSON, CSV, fixed-width, and custom documents.

Separate transport acknowledgement, AS2 MDN, EDI syntax acknowledgement, functional acknowledgement, and business acknowledgement. A successful HTTP response or MDN does not prove business acceptance.

## Migrate safely

Require AS2 message ID, MIC, algorithms, signed receipt, payload hash, and certificate references without exposing private keys. Use checksum and atomic rename, temporary object, or completion marker for MFT.

Rotate certificates with old/new overlap, partner confirmation, and rollback. Certify positive and negative documents, then cut over each partner independently with legacy fallback until stable.
