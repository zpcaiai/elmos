# Elmos Full Product Function Inventory

This human-readable inventory mirrors `matrices/feature-registry.yaml`. The machine-readable registry remains authoritative.

## Identity, Access, Organization and Tenant Governance (`identity-access-tenant`)

Adapter: `external-identity-access-harness`. Contexts: `web-console`, `public-api`, `admin-console`, `service-account`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `identity-access-tenant.account-registration` | Account Registration | P0 | L2 |
| `identity-access-tenant.email-verification` | Email Verification | P0 | L2 |
| `identity-access-tenant.password-login` | Password Login | P0 | L2 |
| `identity-access-tenant.password-reset` | Password Reset | P0 | L2 |
| `identity-access-tenant.logout-session-revocation` | Logout Session Revocation | P0 | L2 |
| `identity-access-tenant.mfa-enrollment-and-challenge` | Mfa Enrollment And Challenge | P0 | L2 |
| `identity-access-tenant.oidc-sso-login` | Oidc Sso Login | P0 | L2 |
| `identity-access-tenant.saml-sso-login` | Saml Sso Login | P0 | L2 |
| `identity-access-tenant.session-expiry-and-rotation` | Session Expiry And Rotation | P0 | L2 |
| `identity-access-tenant.concurrent-session-policy` | Concurrent Session Policy | P0 | L2 |
| `identity-access-tenant.api-key-create-rotate-revoke` | Api Key Create Rotate Revoke | P0 | L2 |
| `identity-access-tenant.service-account-authentication` | Service Account Authentication | P0 | L2 |
| `identity-access-tenant.organization-create-update-delete` | Organization Create Update Delete | P0 | L2 |
| `identity-access-tenant.tenant-data-isolation` | Tenant Data Isolation | P0 | L2 |
| `identity-access-tenant.project-workspace-membership` | Project Workspace Membership | P0 | L2 |
| `identity-access-tenant.rbac-role-assignment` | Rbac Role Assignment | P0 | L2 |
| `identity-access-tenant.abac-resource-policy` | Abac Resource Policy | P0 | L2 |
| `identity-access-tenant.resource-ownership-transfer` | Resource Ownership Transfer | P0 | L2 |
| `identity-access-tenant.invitation-accept-expire-revoke` | Invitation Accept Expire Revoke | P0 | L2 |
| `identity-access-tenant.least-privilege-defaults` | Least Privilege Defaults | P0 | L2 |
| `identity-access-tenant.admin-impersonation-with-consent-and-audit` | Admin Impersonation With Consent And Audit | P0 | L2 |
| `identity-access-tenant.cross-tenant-access-denial` | Cross Tenant Access Denial | P0 | L2 |
| `identity-access-tenant.account-lockout-and-brute-force-defense` | Account Lockout And Brute Force Defense | P0 | L2 |
| `identity-access-tenant.csrf-session-binding` | Csrf Session Binding | P0 | L2 |
| `identity-access-tenant.authentication-event-audit` | Authentication Event Audit | P0 | L2 |
| `identity-access-tenant.authorization-decision-trace` | Authorization Decision Trace | P0 | L2 |
| `identity-access-tenant.user-deletion-and-access-revocation` | User Deletion And Access Revocation | P0 | L2 |
| `identity-access-tenant.tenant-suspension-and-reactivation` | Tenant Suspension And Reactivation | P0 | L2 |
| `identity-access-tenant.passkey-webauthn` | Passkey Webauthn | P1 | L2 |
| `identity-access-tenant.device-session-management` | Device Session Management | P1 | L2 |
| `identity-access-tenant.recovery-codes` | Recovery Codes | P1 | L2 |
| `identity-access-tenant.just-in-time-provisioning` | Just In Time Provisioning | P1 | L2 |
| `identity-access-tenant.scim-user-provisioning` | Scim User Provisioning | P1 | L2 |
| `identity-access-tenant.custom-role-definition` | Custom Role Definition | P1 | L2 |
| `identity-access-tenant.role-inheritance-and-conflict` | Role Inheritance And Conflict | P1 | L2 |
| `identity-access-tenant.group-membership-sync` | Group Membership Sync | P1 | L2 |
| `identity-access-tenant.domain-claim-and-verification` | Domain Claim And Verification | P1 | L2 |
| `identity-access-tenant.organization-policy-inheritance` | Organization Policy Inheritance | P1 | L2 |
| `identity-access-tenant.consent-and-terms-versioning` | Consent And Terms Versioning | P1 | L2 |
| `identity-access-tenant.age-and-region-policy` | Age And Region Policy | P1 | L2 |
| `identity-access-tenant.locale-timezone-profile` | Locale Timezone Profile | P1 | L2 |
| `identity-access-tenant.account-export` | Account Export | P1 | L2 |
| `identity-access-tenant.account-merge-conflict` | Account Merge Conflict | P1 | L2 |
| `identity-access-tenant.inactive-account-retention` | Inactive Account Retention | P1 | L2 |
| `identity-access-tenant.privileged-action-step-up-auth` | Privileged Action Step Up Auth | P1 | L2 |
| `identity-access-tenant.break-glass-access` | Break Glass Access | P1 | L2 |
| `identity-access-tenant.directory-sync-reconciliation` | Directory Sync Reconciliation | P1 | L2 |
| `identity-access-tenant.login-risk-signals` | Login Risk Signals | P1 | L2 |
| `identity-access-tenant.social-login-connect-disconnect` | Social Login Connect Disconnect | P2 | L1 |
| `identity-access-tenant.profile-avatar-and-preferences` | Profile Avatar And Preferences | P2 | L1 |
| `identity-access-tenant.delegated-project-admin` | Delegated Project Admin | P2 | L1 |
| `identity-access-tenant.session-device-labels` | Session Device Labels | P2 | L1 |
| `identity-access-tenant.login-history-export` | Login History Export | P2 | L1 |

## Elmos Product Control Plane, Projects, Jobs and Administration (`platform-control-plane`)

Adapter: `external-control-plane-harness`. Contexts: `web-console`, `public-api`, `event-stream`, `admin-console`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `platform-control-plane.project-create-read-update-delete` | Project Create Read Update Delete | P0 | L2 |
| `platform-control-plane.repository-bind-unbind` | Repository Bind Unbind | P0 | L2 |
| `platform-control-plane.business-line-selection` | Business Line Selection | P0 | L2 |
| `platform-control-plane.source-target-configuration` | Source Target Configuration | P0 | L2 |
| `platform-control-plane.model-selection-and-auto-selection` | Model Selection And Auto Selection | P0 | L2 |
| `platform-control-plane.task-create-submit-start` | Task Create Submit Start | P0 | L2 |
| `platform-control-plane.task-state-machine` | Task State Machine | P0 | L2 |
| `platform-control-plane.task-progress-events` | Task Progress Events | P0 | L2 |
| `platform-control-plane.task-pause-resume-cancel` | Task Pause Resume Cancel | P0 | L2 |
| `platform-control-plane.task-retry-and-compensation` | Task Retry And Compensation | P0 | L2 |
| `platform-control-plane.task-idempotency-key` | Task Idempotency Key | P0 | L2 |
| `platform-control-plane.task-lease-and-fencing` | Task Lease And Fencing | P0 | L2 |
| `platform-control-plane.task-checkpoint-linkage` | Task Checkpoint Linkage | P0 | L2 |
| `platform-control-plane.task-artifact-linkage` | Task Artifact Linkage | P0 | L2 |
| `platform-control-plane.task-cost-and-eta-display` | Task Cost And Eta Display | P0 | L2 |
| `platform-control-plane.per-account-three-task-concurrency` | Per Account Three Task Concurrency | P0 | L2 |
| `platform-control-plane.tenant-quota-enforcement` | Tenant Quota Enforcement | P0 | L2 |
| `platform-control-plane.priority-and-fair-scheduling` | Priority And Fair Scheduling | P0 | L2 |
| `platform-control-plane.backpressure-and-admission-control` | Backpressure And Admission Control | P0 | L2 |
| `platform-control-plane.project-member-permissions` | Project Member Permissions | P0 | L2 |
| `platform-control-plane.project-delete-retention-and-restore` | Project Delete Retention And Restore | P0 | L2 |
| `platform-control-plane.batch-job-submit-and-monitor` | Batch Job Submit And Monitor | P0 | L2 |
| `platform-control-plane.failed-job-triage-linkage` | Failed Job Triage Linkage | P0 | L2 |
| `platform-control-plane.transactional-outbox-publication` | Transactional Outbox Publication | P0 | L2 |
| `platform-control-plane.command-event-correlation` | Command Event Correlation | P0 | L2 |
| `platform-control-plane.admin-safe-job-intervention` | Admin Safe Job Intervention | P0 | L2 |
| `platform-control-plane.audit-log-immutability` | Audit Log Immutability | P0 | L2 |
| `platform-control-plane.feature-flag-consistency` | Feature Flag Consistency | P0 | L2 |
| `platform-control-plane.configuration-versioning` | Configuration Versioning | P0 | L2 |
| `platform-control-plane.environment-profile-binding` | Environment Profile Binding | P0 | L2 |
| `platform-control-plane.release-candidate-binding` | Release Candidate Binding | P0 | L2 |
| `platform-control-plane.plan-digest-binding` | Plan Digest Binding | P0 | L2 |
| `platform-control-plane.unknown-state-fail-closed` | Unknown State Fail Closed | P0 | L2 |
| `platform-control-plane.project-template-clone` | Project Template Clone | P1 | L2 |
| `platform-control-plane.project-archive-unarchive` | Project Archive Unarchive | P1 | L2 |
| `platform-control-plane.task-tag-filter-search` | Task Tag Filter Search | P1 | L2 |
| `platform-control-plane.saved-run-configuration` | Saved Run Configuration | P1 | L2 |
| `platform-control-plane.scheduled-run` | Scheduled Run | P1 | L2 |
| `platform-control-plane.recurring-run` | Recurring Run | P1 | L2 |
| `platform-control-plane.bulk-cancel-pause-resume` | Bulk Cancel Pause Resume | P1 | L2 |
| `platform-control-plane.cross-project-dashboard` | Cross Project Dashboard | P1 | L2 |
| `platform-control-plane.notification-preferences` | Notification Preferences | P1 | L2 |
| `platform-control-plane.webhook-subscription-management` | Webhook Subscription Management | P1 | L2 |
| `platform-control-plane.retention-policy-per-project` | Retention Policy Per Project | P1 | L2 |
| `platform-control-plane.project-export-import` | Project Export Import | P1 | L2 |
| `platform-control-plane.soft-delete-and-legal-hold` | Soft Delete And Legal Hold | P1 | L2 |
| `platform-control-plane.maintenance-mode` | Maintenance Mode | P1 | L2 |
| `platform-control-plane.regional-routing` | Regional Routing | P1 | L2 |
| `platform-control-plane.support-diagnostic-bundle` | Support Diagnostic Bundle | P1 | L2 |
| `platform-control-plane.admin-feature-rollout` | Admin Feature Rollout | P1 | L2 |
| `platform-control-plane.api-rate-limit-and-quota-report` | Api Rate Limit And Quota Report | P1 | L2 |
| `platform-control-plane.task-dependency-dag` | Task Dependency Dag | P1 | L2 |
| `platform-control-plane.subtask-shard-monitoring` | Subtask Shard Monitoring | P1 | L2 |
| `platform-control-plane.orphan-task-recovery` | Orphan Task Recovery | P1 | L2 |
| `platform-control-plane.stuck-task-detection` | Stuck Task Detection | P1 | L2 |
| `platform-control-plane.queue-depth-and-capacity-indicator` | Queue Depth And Capacity Indicator | P1 | L2 |
| `platform-control-plane.estimated-start-time` | Estimated Start Time | P1 | L2 |
| `platform-control-plane.manual-approval-stage` | Manual Approval Stage | P1 | L2 |
| `platform-control-plane.approval-expiry` | Approval Expiry | P1 | L2 |
| `platform-control-plane.change-request-reopen` | Change Request Reopen | P1 | L2 |
| `platform-control-plane.dashboard-personalization` | Dashboard Personalization | P2 | L1 |
| `platform-control-plane.recent-projects` | Recent Projects | P2 | L1 |
| `platform-control-plane.favorite-projects` | Favorite Projects | P2 | L1 |
| `platform-control-plane.saved-filters` | Saved Filters | P2 | L1 |
| `platform-control-plane.bulk-tagging` | Bulk Tagging | P2 | L1 |
| `platform-control-plane.ui-tour-and-onboarding` | Ui Tour And Onboarding | P2 | L1 |

## Repository, Archive and Context Ingestion (`repository-ingestion-context`)

Adapter: `external-ingestion-harness`. Contexts: `git-url`, `archive-upload`, `folder-upload`, `webhook-incremental-sync`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `repository-ingestion-context.github-clone-by-url` | Github Clone By Url | P0 | L2 |
| `repository-ingestion-context.gitlab-clone-by-url` | Gitlab Clone By Url | P0 | L2 |
| `repository-ingestion-context.gitee-clone-by-url` | Gitee Clone By Url | P0 | L2 |
| `repository-ingestion-context.generic-git-clone` | Generic Git Clone | P0 | L2 |
| `repository-ingestion-context.private-repository-credential-broker` | Private Repository Credential Broker | P0 | L2 |
| `repository-ingestion-context.branch-tag-commit-selection` | Branch Tag Commit Selection | P0 | L2 |
| `repository-ingestion-context.commit-pin-and-source-digest` | Commit Pin And Source Digest | P0 | L2 |
| `repository-ingestion-context.zip-upload` | Zip Upload | P0 | L2 |
| `repository-ingestion-context.tar-gz-upload` | Tar Gz Upload | P0 | L2 |
| `repository-ingestion-context.folder-upload` | Folder Upload | P0 | L2 |
| `repository-ingestion-context.archive-path-traversal-defense` | Archive Path Traversal Defense | P0 | L2 |
| `repository-ingestion-context.zip-bomb-defense` | Zip Bomb Defense | P0 | L2 |
| `repository-ingestion-context.symlink-and-hardlink-policy` | Symlink And Hardlink Policy | P0 | L2 |
| `repository-ingestion-context.submodule-resolution` | Submodule Resolution | P0 | L2 |
| `repository-ingestion-context.git-lfs-resolution` | Git Lfs Resolution | P0 | L2 |
| `repository-ingestion-context.monorepo-detection` | Monorepo Detection | P0 | L2 |
| `repository-ingestion-context.multi-repository-project` | Multi Repository Project | P0 | L2 |
| `repository-ingestion-context.language-and-framework-detection` | Language And Framework Detection | P0 | L2 |
| `repository-ingestion-context.build-system-detection` | Build System Detection | P0 | L2 |
| `repository-ingestion-context.dependency-manifest-discovery` | Dependency Manifest Discovery | P0 | L2 |
| `repository-ingestion-context.generated-code-detection` | Generated Code Detection | P0 | L2 |
| `repository-ingestion-context.binary-file-policy` | Binary File Policy | P0 | L2 |
| `repository-ingestion-context.encoding-and-line-ending-detection` | Encoding And Line Ending Detection | P0 | L2 |
| `repository-ingestion-context.ignore-rule-application` | Ignore Rule Application | P0 | L2 |
| `repository-ingestion-context.secret-scanning-before-execution` | Secret Scanning Before Execution | P0 | L2 |
| `repository-ingestion-context.license-detection-and-review-state` | License Detection And Review State | P0 | L2 |
| `repository-ingestion-context.malicious-build-script-quarantine` | Malicious Build Script Quarantine | P0 | L2 |
| `repository-ingestion-context.repository-size-and-file-count-limits` | Repository Size And File Count Limits | P0 | L2 |
| `repository-ingestion-context.content-addressed-fingerprint` | Content Addressed Fingerprint | P0 | L2 |
| `repository-ingestion-context.provenance-chain-preservation` | Provenance Chain Preservation | P0 | L2 |
| `repository-ingestion-context.incremental-commit-sync` | Incremental Commit Sync | P0 | L2 |
| `repository-ingestion-context.webhook-signature-and-deduplication` | Webhook Signature And Deduplication | P0 | L2 |
| `repository-ingestion-context.deleted-file-and-rename-detection` | Deleted File And Rename Detection | P0 | L2 |
| `repository-ingestion-context.repository-access-revocation` | Repository Access Revocation | P0 | L2 |
| `repository-ingestion-context.shallow-clone-fallback` | Shallow Clone Fallback | P1 | L2 |
| `repository-ingestion-context.sparse-checkout` | Sparse Checkout | P1 | L2 |
| `repository-ingestion-context.partial-clone` | Partial Clone | P1 | L2 |
| `repository-ingestion-context.large-file-streaming` | Large File Streaming | P1 | L2 |
| `repository-ingestion-context.nested-archive-policy` | Nested Archive Policy | P1 | L2 |
| `repository-ingestion-context.unusual-file-name-handling` | Unusual File Name Handling | P1 | L2 |
| `repository-ingestion-context.case-sensitive-path-collision` | Case Sensitive Path Collision | P1 | L2 |
| `repository-ingestion-context.unicode-normalization-in-paths` | Unicode Normalization In Paths | P1 | L2 |
| `repository-ingestion-context.vendored-dependency-classification` | Vendored Dependency Classification | P1 | L2 |
| `repository-ingestion-context.test-fixture-identification` | Test Fixture Identification | P1 | L2 |
| `repository-ingestion-context.documentation-and-config-classification` | Documentation And Config Classification | P1 | L2 |
| `repository-ingestion-context.commit-history-window` | Commit History Window | P1 | L2 |
| `repository-ingestion-context.blame-metadata-ingestion` | Blame Metadata Ingestion | P1 | L2 |
| `repository-ingestion-context.issue-pr-linkage` | Issue Pr Linkage | P1 | L2 |
| `repository-ingestion-context.repository-webhook-reconnect` | Repository Webhook Reconnect | P1 | L2 |
| `repository-ingestion-context.incremental-index-checkpoint` | Incremental Index Checkpoint | P1 | L2 |
| `repository-ingestion-context.cache-reuse-by-tree-digest` | Cache Reuse By Tree Digest | P1 | L2 |
| `repository-ingestion-context.stale-cache-invalidation` | Stale Cache Invalidation | P1 | L2 |
| `repository-ingestion-context.repository-mirror-failover` | Repository Mirror Failover | P1 | L2 |
| `repository-ingestion-context.offline-corpus-mirror` | Offline Corpus Mirror | P1 | L2 |
| `repository-ingestion-context.source-snapshot-export` | Source Snapshot Export | P1 | L2 |
| `repository-ingestion-context.repository-timeout-and-resume` | Repository Timeout And Resume | P1 | L2 |
| `repository-ingestion-context.repo-host-rate-limit-recovery` | Repo Host Rate Limit Recovery | P1 | L2 |
| `repository-ingestion-context.credential-scope-minimization` | Credential Scope Minimization | P1 | L2 |
| `repository-ingestion-context.corporate-proxy-support` | Corporate Proxy Support | P1 | L2 |
| `repository-ingestion-context.repository-thumbnail-metadata` | Repository Thumbnail Metadata | P2 | L1 |
| `repository-ingestion-context.recent-branch-list` | Recent Branch List | P2 | L1 |
| `repository-ingestion-context.commit-message-search` | Commit Message Search | P2 | L1 |
| `repository-ingestion-context.author-statistics` | Author Statistics | P2 | L1 |
| `repository-ingestion-context.repository-language-summary` | Repository Language Summary | P2 | L1 |

## Multimodal File and Document Processing (`multimodal-document-processing`)

Adapter: `external-multimodal-processing-harness`. Contexts: `pdf-word-text`, `image`, `audio`, `mixed-bundle`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `multimodal-document-processing.pdf-text-extraction` | Pdf Text Extraction | P0 | L2 |
| `multimodal-document-processing.pdf-page-anchor-preservation` | Pdf Page Anchor Preservation | P0 | L2 |
| `multimodal-document-processing.pdf-table-extraction` | Pdf Table Extraction | P0 | L2 |
| `multimodal-document-processing.pdf-code-block-preservation` | Pdf Code Block Preservation | P0 | L2 |
| `multimodal-document-processing.docx-text-and-heading-extraction` | Docx Text And Heading Extraction | P0 | L2 |
| `multimodal-document-processing.markdown-structure-preservation` | Markdown Structure Preservation | P0 | L2 |
| `multimodal-document-processing.plain-text-encoding` | Plain Text Encoding | P0 | L2 |
| `multimodal-document-processing.image-metadata-and-content-analysis` | Image Metadata And Content Analysis | P0 | L2 |
| `multimodal-document-processing.audio-transcription` | Audio Transcription | P0 | L2 |
| `multimodal-document-processing.audio-language-detection` | Audio Language Detection | P0 | L2 |
| `multimodal-document-processing.mime-sniffing-and-extension-mismatch` | Mime Sniffing And Extension Mismatch | P0 | L2 |
| `multimodal-document-processing.virus-and-malware-scan` | Virus And Malware Scan | P0 | L2 |
| `multimodal-document-processing.encrypted-or-password-protected-file-policy` | Encrypted Or Password Protected File Policy | P0 | L2 |
| `multimodal-document-processing.corrupt-file-failure-report` | Corrupt File Failure Report | P0 | L2 |
| `multimodal-document-processing.file-size-page-count-duration-limits` | File Size Page Count Duration Limits | P0 | L2 |
| `multimodal-document-processing.pii-and-secret-redaction` | Pii And Secret Redaction | P0 | L2 |
| `multimodal-document-processing.attachment-provenance-and-digest` | Attachment Provenance And Digest | P0 | L2 |
| `multimodal-document-processing.page-timecode-citation-links` | Page Timecode Citation Links | P0 | L2 |
| `multimodal-document-processing.prompt-injection-in-document-defense` | Prompt Injection In Document Defense | P0 | L2 |
| `multimodal-document-processing.embedded-object-and-macro-policy` | Embedded Object And Macro Policy | P0 | L2 |
| `multimodal-document-processing.duplicate-file-detection` | Duplicate File Detection | P0 | L2 |
| `multimodal-document-processing.mixed-language-document` | Mixed Language Document | P0 | L2 |
| `multimodal-document-processing.right-to-left-and-cjk-text` | Right To Left And Cjk Text | P0 | L2 |
| `multimodal-document-processing.table-cell-order-and-merged-cells` | Table Cell Order And Merged Cells | P0 | L2 |
| `multimodal-document-processing.diagram-image-reference-preservation` | Diagram Image Reference Preservation | P0 | L2 |
| `multimodal-document-processing.chunking-boundary-integrity` | Chunking Boundary Integrity | P0 | L2 |
| `multimodal-document-processing.document-deletion-index-purge` | Document Deletion Index Purge | P0 | L2 |
| `multimodal-document-processing.tenant-isolated-processing` | Tenant Isolated Processing | P0 | L2 |
| `multimodal-document-processing.temporary-file-cleanup` | Temporary File Cleanup | P0 | L2 |
| `multimodal-document-processing.unsupported-format-disclosure` | Unsupported Format Disclosure | P0 | L2 |
| `multimodal-document-processing.scanned-pdf-fallback` | Scanned Pdf Fallback | P1 | L2 |
| `multimodal-document-processing.handwritten-image-policy` | Handwritten Image Policy | P1 | L2 |
| `multimodal-document-processing.image-rotation-and-exif-orientation` | Image Rotation And Exif Orientation | P1 | L2 |
| `multimodal-document-processing.audio-speaker-diarization` | Audio Speaker Diarization | P1 | L2 |
| `multimodal-document-processing.audio-timestamp-alignment` | Audio Timestamp Alignment | P1 | L2 |
| `multimodal-document-processing.presentation-text-extraction` | Presentation Text Extraction | P1 | L2 |
| `multimodal-document-processing.spreadsheet-sheet-and-cell-extraction` | Spreadsheet Sheet And Cell Extraction | P1 | L2 |
| `multimodal-document-processing.html-sanitization` | Html Sanitization | P1 | L2 |
| `multimodal-document-processing.email-message-extraction` | Email Message Extraction | P1 | L2 |
| `multimodal-document-processing.archive-of-documents` | Archive Of Documents | P1 | L2 |
| `multimodal-document-processing.incremental-document-update` | Incremental Document Update | P1 | L2 |
| `multimodal-document-processing.document-version-diff` | Document Version Diff | P1 | L2 |
| `multimodal-document-processing.semantic-deduplication` | Semantic Deduplication | P1 | L2 |
| `multimodal-document-processing.content-language-translation-boundary` | Content Language Translation Boundary | P1 | L2 |
| `multimodal-document-processing.low-confidence-extraction-label` | Low Confidence Extraction Label | P1 | L2 |
| `multimodal-document-processing.large-document-streaming` | Large Document Streaming | P1 | L2 |
| `multimodal-document-processing.ocr-budget-and-timeout` | Ocr Budget And Timeout | P1 | L2 |
| `multimodal-document-processing.document-classification` | Document Classification | P1 | L2 |
| `multimodal-document-processing.retention-policy` | Retention Policy | P1 | L2 |
| `multimodal-document-processing.legal-hold-exclusion` | Legal Hold Exclusion | P1 | L2 |
| `multimodal-document-processing.thumbnail-generation` | Thumbnail Generation | P2 | L1 |
| `multimodal-document-processing.document-preview` | Document Preview | P2 | L1 |
| `multimodal-document-processing.audio-waveform-preview` | Audio Waveform Preview | P2 | L1 |
| `multimodal-document-processing.page-count-display` | Page Count Display | P2 | L1 |
| `multimodal-document-processing.extraction-quality-dashboard` | Extraction Quality Dashboard | P2 | L1 |

## AI Runtime, Model Routing and Context Management (`ai-runtime-model-routing`)

Adapter: `external-ai-runtime-harness`. Contexts: `synchronous`, `streaming`, `batch`, `fallback-chain`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `ai-runtime-model-routing.provider-registration-and-health` | Provider Registration And Health | P0 | L2 |
| `ai-runtime-model-routing.model-catalog-and-capabilities` | Model Catalog And Capabilities | P0 | L2 |
| `ai-runtime-model-routing.user-selected-model` | User Selected Model | P0 | L2 |
| `ai-runtime-model-routing.automatic-model-selection` | Automatic Model Selection | P0 | L2 |
| `ai-runtime-model-routing.task-specific-model-routing` | Task Specific Model Routing | P0 | L2 |
| `ai-runtime-model-routing.quality-cost-latency-policy` | Quality Cost Latency Policy | P0 | L2 |
| `ai-runtime-model-routing.provider-fallback` | Provider Fallback | P0 | L2 |
| `ai-runtime-model-routing.model-timeout-and-retry` | Model Timeout And Retry | P0 | L2 |
| `ai-runtime-model-routing.rate-limit-backoff` | Rate Limit Backoff | P0 | L2 |
| `ai-runtime-model-routing.circuit-breaker` | Circuit Breaker | P0 | L2 |
| `ai-runtime-model-routing.streaming-token-order` | Streaming Token Order | P0 | L2 |
| `ai-runtime-model-routing.stream-cancel-and-resume-policy` | Stream Cancel And Resume Policy | P0 | L2 |
| `ai-runtime-model-routing.structured-output-schema-validation` | Structured Output Schema Validation | P0 | L2 |
| `ai-runtime-model-routing.tool-call-schema-validation` | Tool Call Schema Validation | P0 | L2 |
| `ai-runtime-model-routing.model-output-malformation-repair-bound` | Model Output Malformation Repair Bound | P0 | L2 |
| `ai-runtime-model-routing.context-window-budget` | Context Window Budget | P0 | L2 |
| `ai-runtime-model-routing.context-compaction` | Context Compaction | P0 | L2 |
| `ai-runtime-model-routing.context-truncation-disclosure` | Context Truncation Disclosure | P0 | L2 |
| `ai-runtime-model-routing.prompt-template-versioning` | Prompt Template Versioning | P0 | L2 |
| `ai-runtime-model-routing.system-instruction-precedence` | System Instruction Precedence | P0 | L2 |
| `ai-runtime-model-routing.untrusted-context-separation` | Untrusted Context Separation | P0 | L2 |
| `ai-runtime-model-routing.response-citation-requirement` | Response Citation Requirement | P0 | L2 |
| `ai-runtime-model-routing.hallucination-and-unsupported-claim-detection` | Hallucination And Unsupported Claim Detection | P0 | L2 |
| `ai-runtime-model-routing.safety-refusal-policy` | Safety Refusal Policy | P0 | L2 |
| `ai-runtime-model-routing.deterministic-seed-recording` | Deterministic Seed Recording | P0 | L2 |
| `ai-runtime-model-routing.temperature-and-sampling-recording` | Temperature And Sampling Recording | P0 | L2 |
| `ai-runtime-model-routing.input-output-token-accounting` | Input Output Token Accounting | P0 | L2 |
| `ai-runtime-model-routing.provider-usage-deduplication` | Provider Usage Deduplication | P0 | L2 |
| `ai-runtime-model-routing.model-revision-freeze` | Model Revision Freeze | P0 | L2 |
| `ai-runtime-model-routing.model-drift-detection` | Model Drift Detection | P0 | L2 |
| `ai-runtime-model-routing.multi-model-judge-independence` | Multi Model Judge Independence | P0 | L2 |
| `ai-runtime-model-routing.no-hidden-test-exposure` | No Hidden Test Exposure | P0 | L2 |
| `ai-runtime-model-routing.prompt-secret-redaction` | Prompt Secret Redaction | P0 | L2 |
| `ai-runtime-model-routing.cache-key-authority-and-tenant-scope` | Cache Key Authority And Tenant Scope | P0 | L2 |
| `ai-runtime-model-routing.cache-hit-correctness` | Cache Hit Correctness | P0 | L2 |
| `ai-runtime-model-routing.cache-invalidation-on-prompt-model-skill-change` | Cache Invalidation On Prompt Model Skill Change | P0 | L2 |
| `ai-runtime-model-routing.provider-data-retention-policy` | Provider Data Retention Policy | P0 | L2 |
| `ai-runtime-model-routing.speculative-routing` | Speculative Routing | P1 | L2 |
| `ai-runtime-model-routing.parallel-model-candidates` | Parallel Model Candidates | P1 | L2 |
| `ai-runtime-model-routing.ensemble-consensus` | Ensemble Consensus | P1 | L2 |
| `ai-runtime-model-routing.model-specialization-by-language` | Model Specialization By Language | P1 | L2 |
| `ai-runtime-model-routing.model-specialization-by-repository-size` | Model Specialization By Repository Size | P1 | L2 |
| `ai-runtime-model-routing.adaptive-token-budget` | Adaptive Token Budget | P1 | L2 |
| `ai-runtime-model-routing.early-exit-on-proof` | Early Exit On Proof | P1 | L2 |
| `ai-runtime-model-routing.quality-estimation-before-generation` | Quality Estimation Before Generation | P1 | L2 |
| `ai-runtime-model-routing.shadow-provider-evaluation` | Shadow Provider Evaluation | P1 | L2 |
| `ai-runtime-model-routing.provider-region-routing` | Provider Region Routing | P1 | L2 |
| `ai-runtime-model-routing.provider-egress-policy` | Provider Egress Policy | P1 | L2 |
| `ai-runtime-model-routing.streaming-time-to-first-token` | Streaming Time To First Token | P1 | L2 |
| `ai-runtime-model-routing.response-length-control` | Response Length Control | P1 | L2 |
| `ai-runtime-model-routing.reasoning-effort-policy` | Reasoning Effort Policy | P1 | L2 |
| `ai-runtime-model-routing.fallback-quality-non-inferiority` | Fallback Quality Non Inferiority | P1 | L2 |
| `ai-runtime-model-routing.prompt-ab-test-with-holdout` | Prompt Ab Test With Holdout | P1 | L2 |
| `ai-runtime-model-routing.semantic-cache` | Semantic Cache | P1 | L2 |
| `ai-runtime-model-routing.prefix-cache` | Prefix Cache | P1 | L2 |
| `ai-runtime-model-routing.conversation-summary-memory` | Conversation Summary Memory | P1 | L2 |
| `ai-runtime-model-routing.provider-billing-reconciliation` | Provider Billing Reconciliation | P1 | L2 |
| `ai-runtime-model-routing.batch-api-resume` | Batch Api Resume | P1 | L2 |
| `ai-runtime-model-routing.partial-response-recovery` | Partial Response Recovery | P1 | L2 |
| `ai-runtime-model-routing.request-id-correlation` | Request Id Correlation | P1 | L2 |
| `ai-runtime-model-routing.provider-error-normalization` | Provider Error Normalization | P1 | L2 |
| `ai-runtime-model-routing.provider-capability-negotiation` | Provider Capability Negotiation | P1 | L2 |
| `ai-runtime-model-routing.model-favorites` | Model Favorites | P2 | L1 |
| `ai-runtime-model-routing.model-display-metadata` | Model Display Metadata | P2 | L1 |
| `ai-runtime-model-routing.estimated-cost-preview` | Estimated Cost Preview | P2 | L1 |
| `ai-runtime-model-routing.estimated-latency-preview` | Estimated Latency Preview | P2 | L1 |
| `ai-runtime-model-routing.provider-status-page-link` | Provider Status Page Link | P2 | L1 |

## Agent, Tool, MCP, A2A, AG-UI and Harness Protocols (`agent-protocol-tooling`)

Adapter: `external-agent-protocol-harness`. Contexts: `mcp`, `a2a`, `ag-ui`, `local-or-remote-tool`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `agent-protocol-tooling.tool-registry-discovery` | Tool Registry Discovery | P0 | L2 |
| `agent-protocol-tooling.tool-schema-and-version-negotiation` | Tool Schema And Version Negotiation | P0 | L2 |
| `agent-protocol-tooling.tool-whitelist` | Tool Whitelist | P0 | L2 |
| `agent-protocol-tooling.parameter-level-authorization` | Parameter Level Authorization | P0 | L2 |
| `agent-protocol-tooling.environment-owned-authority` | Environment Owned Authority | P0 | L2 |
| `agent-protocol-tooling.attachment-owned-authority` | Attachment Owned Authority | P0 | L2 |
| `agent-protocol-tooling.invocation-scoped-capability-lease` | Invocation Scoped Capability Lease | P0 | L2 |
| `agent-protocol-tooling.lease-expiry-before-side-effect` | Lease Expiry Before Side Effect | P0 | L2 |
| `agent-protocol-tooling.verified-security-context` | Verified Security Context | P0 | L2 |
| `agent-protocol-tooling.secret-broker-short-lived-token` | Secret Broker Short Lived Token | P0 | L2 |
| `agent-protocol-tooling.network-egress-deny-by-default` | Network Egress Deny By Default | P0 | L2 |
| `agent-protocol-tooling.filesystem-root-policy` | Filesystem Root Policy | P0 | L2 |
| `agent-protocol-tooling.sandbox-process-policy` | Sandbox Process Policy | P0 | L2 |
| `agent-protocol-tooling.remote-executor-generation-and-fencing` | Remote Executor Generation And Fencing | P0 | L2 |
| `agent-protocol-tooling.workspace-ownership-and-handoff` | Workspace Ownership And Handoff | P0 | L2 |
| `agent-protocol-tooling.tool-result-raw-intercept-commit-publish-lifecycle` | Tool Result Raw Intercept Commit Publish Lifecycle | P0 | L2 |
| `agent-protocol-tooling.tool-result-size-and-content-policy` | Tool Result Size And Content Policy | P0 | L2 |
| `agent-protocol-tooling.tool-output-secret-redaction` | Tool Output Secret Redaction | P0 | L2 |
| `agent-protocol-tooling.tool-idempotency-key` | Tool Idempotency Key | P0 | L2 |
| `agent-protocol-tooling.human-approval-before-sensitive-tool` | Human Approval Before Sensitive Tool | P0 | L2 |
| `agent-protocol-tooling.approval-binding-to-exact-arguments` | Approval Binding To Exact Arguments | P0 | L2 |
| `agent-protocol-tooling.approval-expiry-and-revocation` | Approval Expiry And Revocation | P0 | L2 |
| `agent-protocol-tooling.mcp-tool-resource-prompt-discovery` | Mcp Tool Resource Prompt Discovery | P0 | L2 |
| `agent-protocol-tooling.mcp-elicitation-authority` | Mcp Elicitation Authority | P0 | L2 |
| `agent-protocol-tooling.mcp-sampling-policy` | Mcp Sampling Policy | P0 | L2 |
| `agent-protocol-tooling.mcp-server-owner-permission-profile` | Mcp Server Owner Permission Profile | P0 | L2 |
| `agent-protocol-tooling.mcp-refresh-without-authority-drift` | Mcp Refresh Without Authority Drift | P0 | L2 |
| `agent-protocol-tooling.a2a-agent-identity` | A2A Agent Identity | P0 | L2 |
| `agent-protocol-tooling.a2a-capability-description` | A2A Capability Description | P0 | L2 |
| `agent-protocol-tooling.a2a-message-authentication` | A2A Message Authentication | P0 | L2 |
| `agent-protocol-tooling.a2a-task-state-and-cancellation` | A2A Task State And Cancellation | P0 | L2 |
| `agent-protocol-tooling.ag-ui-event-order-and-reconnect` | Ag Ui Event Order And Reconnect | P0 | L2 |
| `agent-protocol-tooling.typed-external-ingress` | Typed External Ingress | P0 | L2 |
| `agent-protocol-tooling.registered-durable-plugin-events` | Registered Durable Plugin Events | P0 | L2 |
| `agent-protocol-tooling.subagent-model-execution-spec` | Subagent Model Execution Spec | P0 | L2 |
| `agent-protocol-tooling.per-step-finalized-execution-plan` | Per Step Finalized Execution Plan | P0 | L2 |
| `agent-protocol-tooling.tool-call-audit-and-trace` | Tool Call Audit And Trace | P0 | L2 |
| `agent-protocol-tooling.side-effect-receipt-and-compensation` | Side Effect Receipt And Compensation | P0 | L2 |
| `agent-protocol-tooling.unknown-tool-fail-closed` | Unknown Tool Fail Closed | P0 | L2 |
| `agent-protocol-tooling.prompt-injection-cannot-elevate-tool-authority` | Prompt Injection Cannot Elevate Tool Authority | P0 | L2 |
| `agent-protocol-tooling.tool-capability-cache-invalidation` | Tool Capability Cache Invalidation | P1 | L2 |
| `agent-protocol-tooling.protocol-version-downgrade-policy` | Protocol Version Downgrade Policy | P1 | L2 |
| `agent-protocol-tooling.transport-reconnect-and-replay` | Transport Reconnect And Replay | P1 | L2 |
| `agent-protocol-tooling.long-running-tool-progress` | Long Running Tool Progress | P1 | L2 |
| `agent-protocol-tooling.tool-streaming-output` | Tool Streaming Output | P1 | L2 |
| `agent-protocol-tooling.tool-cancel-propagation` | Tool Cancel Propagation | P1 | L2 |
| `agent-protocol-tooling.nested-agent-authority-reduction` | Nested Agent Authority Reduction | P1 | L2 |
| `agent-protocol-tooling.cross-agent-delegation-proof` | Cross Agent Delegation Proof | P1 | L2 |
| `agent-protocol-tooling.agent-memory-boundary` | Agent Memory Boundary | P1 | L2 |
| `agent-protocol-tooling.agent-loop-budget` | Agent Loop Budget | P1 | L2 |
| `agent-protocol-tooling.infinite-loop-detection` | Infinite Loop Detection | P1 | L2 |
| `agent-protocol-tooling.duplicate-tool-call-suppression` | Duplicate Tool Call Suppression | P1 | L2 |
| `agent-protocol-tooling.tool-result-semantic-validation` | Tool Result Semantic Validation | P1 | L2 |
| `agent-protocol-tooling.plugin-signature-and-provenance` | Plugin Signature And Provenance | P1 | L2 |
| `agent-protocol-tooling.skill-trust-domain` | Skill Trust Domain | P1 | L2 |
| `agent-protocol-tooling.agent-marketplace-package-policy` | Agent Marketplace Package Policy | P1 | L2 |
| `agent-protocol-tooling.remote-tool-latency-budget` | Remote Tool Latency Budget | P1 | L2 |
| `agent-protocol-tooling.tool-health-and-circuit-breaker` | Tool Health And Circuit Breaker | P1 | L2 |
| `agent-protocol-tooling.tool-schema-drift-detection` | Tool Schema Drift Detection | P1 | L2 |
| `agent-protocol-tooling.tool-deprecation` | Tool Deprecation | P1 | L2 |
| `agent-protocol-tooling.tool-catalog-search` | Tool Catalog Search | P2 | L1 |
| `agent-protocol-tooling.tool-usage-dashboard` | Tool Usage Dashboard | P2 | L1 |
| `agent-protocol-tooling.agent-topology-visualization` | Agent Topology Visualization | P2 | L1 |
| `agent-protocol-tooling.tool-debug-console` | Tool Debug Console | P2 | L1 |
| `agent-protocol-tooling.protocol-capability-export` | Protocol Capability Export | P2 | L1 |

## RAG, Knowledge Base, Search, Reranking and Memory (`rag-memory-knowledge`)

Adapter: `external-rag-memory-harness`. Contexts: `small-corpus`, `large-corpus`, `multi-tenant`, `incremental-update`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `rag-memory-knowledge.document-parse-and-chunk` | Document Parse And Chunk | P0 | L2 |
| `rag-memory-knowledge.chunk-overlap-and-boundaries` | Chunk Overlap And Boundaries | P0 | L2 |
| `rag-memory-knowledge.embedding-generation` | Embedding Generation | P0 | L2 |
| `rag-memory-knowledge.embedding-model-version-freeze` | Embedding Model Version Freeze | P0 | L2 |
| `rag-memory-knowledge.vector-index-build` | Vector Index Build | P0 | L2 |
| `rag-memory-knowledge.hybrid-dense-sparse-search` | Hybrid Dense Sparse Search | P0 | L2 |
| `rag-memory-knowledge.metadata-filtering` | Metadata Filtering | P0 | L2 |
| `rag-memory-knowledge.tenant-and-document-acl-filtering` | Tenant And Document Acl Filtering | P0 | L2 |
| `rag-memory-knowledge.reranking` | Reranking | P0 | L2 |
| `rag-memory-knowledge.query-rewrite` | Query Rewrite | P0 | L2 |
| `rag-memory-knowledge.multi-query-retrieval` | Multi Query Retrieval | P0 | L2 |
| `rag-memory-knowledge.multi-hop-retrieval` | Multi Hop Retrieval | P0 | L2 |
| `rag-memory-knowledge.graph-rag` | Graph Rag | P0 | L2 |
| `rag-memory-knowledge.citation-source-anchor` | Citation Source Anchor | P0 | L2 |
| `rag-memory-knowledge.citation-completeness` | Citation Completeness | P0 | L2 |
| `rag-memory-knowledge.answer-faithfulness` | Answer Faithfulness | P0 | L2 |
| `rag-memory-knowledge.answer-relevance` | Answer Relevance | P0 | L2 |
| `rag-memory-knowledge.no-answer-when-evidence-missing` | No Answer When Evidence Missing | P0 | L2 |
| `rag-memory-knowledge.freshness-after-document-update` | Freshness After Document Update | P0 | L2 |
| `rag-memory-knowledge.deletion-and-right-to-be-forgotten-purge` | Deletion And Right To Be Forgotten Purge | P0 | L2 |
| `rag-memory-knowledge.index-rebuild-and-cutover` | Index Rebuild And Cutover | P0 | L2 |
| `rag-memory-knowledge.index-checkpoint-and-resume` | Index Checkpoint And Resume | P0 | L2 |
| `rag-memory-knowledge.retrieval-timeout-fallback` | Retrieval Timeout Fallback | P0 | L2 |
| `rag-memory-knowledge.knowledge-base-prompt-injection-defense` | Knowledge Base Prompt Injection Defense | P0 | L2 |
| `rag-memory-knowledge.retrieval-poisoning-detection` | Retrieval Poisoning Detection | P0 | L2 |
| `rag-memory-knowledge.cross-tenant-retrieval-denial` | Cross Tenant Retrieval Denial | P0 | L2 |
| `rag-memory-knowledge.pii-redaction-in-retrieval` | Pii Redaction In Retrieval | P0 | L2 |
| `rag-memory-knowledge.secret-redaction-in-answer` | Secret Redaction In Answer | P0 | L2 |
| `rag-memory-knowledge.working-memory-isolation` | Working Memory Isolation | P0 | L2 |
| `rag-memory-knowledge.episodic-memory-write-read` | Episodic Memory Write Read | P0 | L2 |
| `rag-memory-knowledge.semantic-memory-write-read` | Semantic Memory Write Read | P0 | L2 |
| `rag-memory-knowledge.memory-ttl-and-expiry` | Memory Ttl And Expiry | P0 | L2 |
| `rag-memory-knowledge.memory-user-view-edit-delete` | Memory User View Edit Delete | P0 | L2 |
| `rag-memory-knowledge.memory-consent-and-scope` | Memory Consent And Scope | P0 | L2 |
| `rag-memory-knowledge.memory-summarization-loss-detection` | Memory Summarization Loss Detection | P0 | L2 |
| `rag-memory-knowledge.memory-prompt-injection-defense` | Memory Prompt Injection Defense | P0 | L2 |
| `rag-memory-knowledge.memory-not-used-outside-purpose` | Memory Not Used Outside Purpose | P0 | L2 |
| `rag-memory-knowledge.late-interaction-retrieval` | Late Interaction Retrieval | P1 | L2 |
| `rag-memory-knowledge.parent-child-retrieval` | Parent Child Retrieval | P1 | L2 |
| `rag-memory-knowledge.section-aware-chunking` | Section Aware Chunking | P1 | L2 |
| `rag-memory-knowledge.code-aware-chunking` | Code Aware Chunking | P1 | L2 |
| `rag-memory-knowledge.table-aware-retrieval` | Table Aware Retrieval | P1 | L2 |
| `rag-memory-knowledge.image-and-audio-multimodal-retrieval` | Image And Audio Multimodal Retrieval | P1 | L2 |
| `rag-memory-knowledge.cross-lingual-retrieval` | Cross Lingual Retrieval | P1 | L2 |
| `rag-memory-knowledge.query-expansion` | Query Expansion | P1 | L2 |
| `rag-memory-knowledge.retrieval-diversity` | Retrieval Diversity | P1 | L2 |
| `rag-memory-knowledge.deduplication` | Deduplication | P1 | L2 |
| `rag-memory-knowledge.embedding-drift-detection` | Embedding Drift Detection | P1 | L2 |
| `rag-memory-knowledge.index-compaction` | Index Compaction | P1 | L2 |
| `rag-memory-knowledge.online-offline-eval-correlation` | Online Offline Eval Correlation | P1 | L2 |
| `rag-memory-knowledge.golden-question-set` | Golden Question Set | P1 | L2 |
| `rag-memory-knowledge.hard-negative-set` | Hard Negative Set | P1 | L2 |
| `rag-memory-knowledge.retrieval-latency-and-cost` | Retrieval Latency And Cost | P1 | L2 |
| `rag-memory-knowledge.cache-hit-correctness` | Cache Hit Correctness | P1 | L2 |
| `rag-memory-knowledge.cache-stale-answer-prevention` | Cache Stale Answer Prevention | P1 | L2 |
| `rag-memory-knowledge.memory-conflict-resolution` | Memory Conflict Resolution | P1 | L2 |
| `rag-memory-knowledge.memory-provenance` | Memory Provenance | P1 | L2 |
| `rag-memory-knowledge.personalization-without-tenant-leakage` | Personalization Without Tenant Leakage | P1 | L2 |
| `rag-memory-knowledge.knowledge-base-versioning` | Knowledge Base Versioning | P1 | L2 |
| `rag-memory-knowledge.source-license-and-retention` | Source License And Retention | P1 | L2 |
| `rag-memory-knowledge.vector-store-adapter-conformance` | Vector Store Adapter Conformance | P1 | L2 |
| `rag-memory-knowledge.reranker-adapter-conformance` | Reranker Adapter Conformance | P1 | L2 |
| `rag-memory-knowledge.knowledge-base-dashboard` | Knowledge Base Dashboard | P2 | L1 |
| `rag-memory-knowledge.document-processing-status` | Document Processing Status | P2 | L1 |
| `rag-memory-knowledge.retrieval-debug-view` | Retrieval Debug View | P2 | L1 |
| `rag-memory-knowledge.citation-preview` | Citation Preview | P2 | L1 |
| `rag-memory-knowledge.memory-usage-summary` | Memory Usage Summary | P2 | L1 |

## Repository Intelligence, Code Reading and Architecture Understanding (`project-intelligence`)

Adapter: `external-project-intelligence-harness`. Contexts: `single-repository`, `monorepo`, `multi-repository-system`, `runtime-trace-fused`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `project-intelligence.repository-manifest-and-fingerprint` | Repository Manifest And Fingerprint | P0 | L2 |
| `project-intelligence.multilingual-parser-coverage` | Multilingual Parser Coverage | P0 | L2 |
| `project-intelligence.symbol-index` | Symbol Index | P0 | L2 |
| `project-intelligence.definition-reference-navigation` | Definition Reference Navigation | P0 | L2 |
| `project-intelligence.call-graph` | Call Graph | P0 | L2 |
| `project-intelligence.dependency-graph` | Dependency Graph | P0 | L2 |
| `project-intelligence.module-and-boundary-discovery` | Module And Boundary Discovery | P0 | L2 |
| `project-intelligence.entrypoint-discovery` | Entrypoint Discovery | P0 | L2 |
| `project-intelligence.configuration-and-profile-discovery` | Configuration And Profile Discovery | P0 | L2 |
| `project-intelligence.database-schema-and-orm-map` | Database Schema And Orm Map | P0 | L2 |
| `project-intelligence.api-route-and-contract-map` | Api Route And Contract Map | P0 | L2 |
| `project-intelligence.event-message-topology` | Event Message Topology | P0 | L2 |
| `project-intelligence.data-flow-and-lineage` | Data Flow And Lineage | P0 | L2 |
| `project-intelligence.business-capability-map` | Business Capability Map | P0 | L2 |
| `project-intelligence.business-and-technical-flow-discovery` | Business And Technical Flow Discovery | P0 | L2 |
| `project-intelligence.runtime-trace-static-graph-fusion` | Runtime Trace Static Graph Fusion | P0 | L2 |
| `project-intelligence.online-code-reader` | Online Code Reader | P0 | L2 |
| `project-intelligence.semantic-navigation` | Semantic Navigation | P0 | L2 |
| `project-intelligence.code-explanation-with-source-evidence` | Code Explanation With Source Evidence | P0 | L2 |
| `project-intelligence.project-onboarding-guide` | Project Onboarding Guide | P0 | L2 |
| `project-intelligence.architecture-overview` | Architecture Overview | P0 | L2 |
| `project-intelligence.confirmed-inferred-unknown-recommended-labels` | Confirmed Inferred Unknown Recommended Labels | P0 | L2 |
| `project-intelligence.evidence-link-to-file-line-symbol` | Evidence Link To File Line Symbol | P0 | L2 |
| `project-intelligence.project-search` | Project Search | P0 | L2 |
| `project-intelligence.evidence-grounded-project-qa` | Evidence Grounded Project Qa | P0 | L2 |
| `project-intelligence.change-impact-analysis` | Change Impact Analysis | P0 | L2 |
| `project-intelligence.test-impact-selection` | Test Impact Selection | P0 | L2 |
| `project-intelligence.architecture-rule-check` | Architecture Rule Check | P0 | L2 |
| `project-intelligence.architecture-drift-detection` | Architecture Drift Detection | P0 | L2 |
| `project-intelligence.risk-hotspot-and-technical-debt` | Risk Hotspot And Technical Debt | P0 | L2 |
| `project-intelligence.security-threat-model` | Security Threat Model | P0 | L2 |
| `project-intelligence.large-repository-sharding` | Large Repository Sharding | P0 | L2 |
| `project-intelligence.incremental-analysis-cache` | Incremental Analysis Cache | P0 | L2 |
| `project-intelligence.commit-to-commit-diff-analysis` | Commit To Commit Diff Analysis | P0 | L2 |
| `project-intelligence.multi-repo-service-dependency` | Multi Repo Service Dependency | P0 | L2 |
| `project-intelligence.analysis-version-and-candidate-binding` | Analysis Version And Candidate Binding | P0 | L2 |
| `project-intelligence.human-correction-and-lock` | Human Correction And Lock | P0 | L2 |
| `project-intelligence.unsupported-language-gap-disclosure` | Unsupported Language Gap Disclosure | P0 | L2 |
| `project-intelligence.stale-intelligence-detection` | Stale Intelligence Detection | P0 | L2 |
| `project-intelligence.domain-model-extraction` | Domain Model Extraction | P1 | L2 |
| `project-intelligence.state-machine-discovery` | State Machine Discovery | P1 | L2 |
| `project-intelligence.transaction-boundary-map` | Transaction Boundary Map | P1 | L2 |
| `project-intelligence.cache-topology` | Cache Topology | P1 | L2 |
| `project-intelligence.scheduler-and-job-map` | Scheduler And Job Map | P1 | L2 |
| `project-intelligence.feature-flag-map` | Feature Flag Map | P1 | L2 |
| `project-intelligence.permission-model-map` | Permission Model Map | P1 | L2 |
| `project-intelligence.external-system-integration-map` | External System Integration Map | P1 | L2 |
| `project-intelligence.deployment-topology` | Deployment Topology | P1 | L2 |
| `project-intelligence.cloud-resource-map` | Cloud Resource Map | P1 | L2 |
| `project-intelligence.cost-driver-analysis` | Cost Driver Analysis | P1 | L2 |
| `project-intelligence.ownership-codeowners-map` | Ownership Codeowners Map | P1 | L2 |
| `project-intelligence.churn-and-defect-hotspot` | Churn And Defect Hotspot | P1 | L2 |
| `project-intelligence.dead-code-candidate` | Dead Code Candidate | P1 | L2 |
| `project-intelligence.duplicate-logic-candidate` | Duplicate Logic Candidate | P1 | L2 |
| `project-intelligence.migration-readiness-score` | Migration Readiness Score | P1 | L2 |
| `project-intelligence.modernization-opportunity-map` | Modernization Opportunity Map | P1 | L2 |
| `project-intelligence.test-quality-map` | Test Quality Map | P1 | L2 |
| `project-intelligence.observability-coverage-map` | Observability Coverage Map | P1 | L2 |
| `project-intelligence.documentation-drift` | Documentation Drift | P1 | L2 |
| `project-intelligence.runtime-only-edge-discovery` | Runtime Only Edge Discovery | P1 | L2 |
| `project-intelligence.graph-query-api` | Graph Query Api | P1 | L2 |
| `project-intelligence.project-mind-map` | Project Mind Map | P1 | L2 |
| `project-intelligence.learning-path-by-role` | Learning Path By Role | P1 | L2 |
| `project-intelligence.cross-language-source-target-correspondence` | Cross Language Source Target Correspondence | P1 | L2 |
| `project-intelligence.generated-project-explanation` | Generated Project Explanation | P1 | L2 |
| `project-intelligence.conversion-proof-visualization` | Conversion Proof Visualization | P1 | L2 |
| `project-intelligence.bookmark-and-annotation` | Bookmark And Annotation | P2 | L1 |
| `project-intelligence.reader-theme-and-layout` | Reader Theme And Layout | P2 | L1 |
| `project-intelligence.recent-symbols` | Recent Symbols | P2 | L1 |
| `project-intelligence.saved-queries` | Saved Queries | P2 | L1 |
| `project-intelligence.shareable-deep-link` | Shareable Deep Link | P2 | L1 |

## Online IDE, Build, Debug and Record-Replay (`online-ide-debug`)

Adapter: `external-online-ide-debug-harness`. Contexts: `browser-ide`, `sandbox-executor`, `remote-debug-adapter`, `distributed-system`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `online-ide-debug.file-tree-open-create-rename-delete` | File Tree Open Create Rename Delete | P0 | L2 |
| `online-ide-debug.editor-read-write-and-autosave` | Editor Read Write And Autosave | P0 | L2 |
| `online-ide-debug.encoding-line-ending-preservation` | Encoding Line Ending Preservation | P0 | L2 |
| `online-ide-debug.search-and-replace` | Search And Replace | P0 | L2 |
| `online-ide-debug.symbol-navigation` | Symbol Navigation | P0 | L2 |
| `online-ide-debug.source-diff-and-merge` | Source Diff And Merge | P0 | L2 |
| `online-ide-debug.user-owned-region-protection` | User Owned Region Protection | P0 | L2 |
| `online-ide-debug.terminal-command-sandbox` | Terminal Command Sandbox | P0 | L2 |
| `online-ide-debug.build-command` | Build Command | P0 | L2 |
| `online-ide-debug.unit-test-run` | Unit Test Run | P0 | L2 |
| `online-ide-debug.integration-test-run` | Integration Test Run | P0 | L2 |
| `online-ide-debug.debug-adapter-capability-negotiation` | Debug Adapter Capability Negotiation | P0 | L2 |
| `online-ide-debug.launch-and-attach-debug` | Launch And Attach Debug | P0 | L2 |
| `online-ide-debug.breakpoint-set-remove-conditional` | Breakpoint Set Remove Conditional | P0 | L2 |
| `online-ide-debug.step-over-into-out` | Step Over Into Out | P0 | L2 |
| `online-ide-debug.continue-pause-stop` | Continue Pause Stop | P0 | L2 |
| `online-ide-debug.variables-scope-watch-evaluate` | Variables Scope Watch Evaluate | P0 | L2 |
| `online-ide-debug.call-stack-and-thread-view` | Call Stack And Thread View | P0 | L2 |
| `online-ide-debug.exception-breakpoints` | Exception Breakpoints | P0 | L2 |
| `online-ide-debug.source-map-and-generated-source` | Source Map And Generated Source | P0 | L2 |
| `online-ide-debug.remote-executor-auth-and-fencing` | Remote Executor Auth And Fencing | P0 | L2 |
| `online-ide-debug.debug-session-isolation` | Debug Session Isolation | P0 | L2 |
| `online-ide-debug.debug-secret-redaction` | Debug Secret Redaction | P0 | L2 |
| `online-ide-debug.resource-and-time-limit` | Resource And Time Limit | P0 | L2 |
| `online-ide-debug.network-policy` | Network Policy | P0 | L2 |
| `online-ide-debug.record-and-replay` | Record And Replay | P0 | L2 |
| `online-ide-debug.checkpoint-and-rewind` | Checkpoint And Rewind | P0 | L2 |
| `online-ide-debug.distributed-trace-correlation` | Distributed Trace Correlation | P0 | L2 |
| `online-ide-debug.async-causality` | Async Causality | P0 | L2 |
| `online-ide-debug.message-event-correlation` | Message Event Correlation | P0 | L2 |
| `online-ide-debug.source-target-differential-debug` | Source Target Differential Debug | P0 | L2 |
| `online-ide-debug.crash-recovery-of-session` | Crash Recovery Of Session | P0 | L2 |
| `online-ide-debug.collaborative-edit-conflict` | Collaborative Edit Conflict | P0 | L2 |
| `online-ide-debug.preview-server-sandbox` | Preview Server Sandbox | P0 | L2 |
| `online-ide-debug.artifact-download-integrity` | Artifact Download Integrity | P0 | L2 |
| `online-ide-debug.audit-of-debug-actions` | Audit Of Debug Actions | P0 | L2 |
| `online-ide-debug.malicious-repository-defense` | Malicious Repository Defense | P0 | L2 |
| `online-ide-debug.code-completion-provider-routing` | Code Completion Provider Routing | P1 | L2 |
| `online-ide-debug.inline-explanation` | Inline Explanation | P1 | L2 |
| `online-ide-debug.refactor-preview` | Refactor Preview | P1 | L2 |
| `online-ide-debug.test-generation-preview` | Test Generation Preview | P1 | L2 |
| `online-ide-debug.hot-reload` | Hot Reload | P1 | L2 |
| `online-ide-debug.container-log-view` | Container Log View | P1 | L2 |
| `online-ide-debug.database-query-console-readonly-policy` | Database Query Console Readonly Policy | P1 | L2 |
| `online-ide-debug.performance-profiler` | Performance Profiler | P1 | L2 |
| `online-ide-debug.memory-profiler` | Memory Profiler | P1 | L2 |
| `online-ide-debug.thread-deadlock-view` | Thread Deadlock View | P1 | L2 |
| `online-ide-debug.coverage-overlay` | Coverage Overlay | P1 | L2 |
| `online-ide-debug.mutation-test-view` | Mutation Test View | P1 | L2 |
| `online-ide-debug.debug-share-session-with-approval` | Debug Share Session With Approval | P1 | L2 |
| `online-ide-debug.session-expiry` | Session Expiry | P1 | L2 |
| `online-ide-debug.terminal-history-redaction` | Terminal History Redaction | P1 | L2 |
| `online-ide-debug.workspace-snapshot` | Workspace Snapshot | P1 | L2 |
| `online-ide-debug.workspace-fork` | Workspace Fork | P1 | L2 |
| `online-ide-debug.extension-plugin-policy` | Extension Plugin Policy | P1 | L2 |
| `online-ide-debug.language-server-restart` | Language Server Restart | P1 | L2 |
| `online-ide-debug.large-file-editor` | Large File Editor | P1 | L2 |
| `online-ide-debug.binary-file-preview` | Binary File Preview | P1 | L2 |
| `online-ide-debug.git-status-commit-branch` | Git Status Commit Branch | P1 | L2 |
| `online-ide-debug.pull-request-diff-review` | Pull Request Diff Review | P1 | L2 |
| `online-ide-debug.editor-theme` | Editor Theme | P2 | L1 |
| `online-ide-debug.keyboard-shortcut-map` | Keyboard Shortcut Map | P2 | L1 |
| `online-ide-debug.layout-persistence` | Layout Persistence | P2 | L1 |
| `online-ide-debug.recent-workspaces` | Recent Workspaces | P2 | L1 |
| `online-ide-debug.command-palette-search` | Command Palette Search | P2 | L1 |

## Diagrams, Documents, Presentations and Delivery Artifacts (`artifact-document-diagram`)

Adapter: `external-artifact-render-harness`. Contexts: `analyzed-repository`, `generated-project`, `converted-project`, `modernized-project`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `artifact-document-diagram.architecture-document-generation` | Architecture Document Generation | P0 | L2 |
| `artifact-document-diagram.module-documentation` | Module Documentation | P0 | L2 |
| `artifact-document-diagram.api-documentation` | Api Documentation | P0 | L2 |
| `artifact-document-diagram.data-dictionary` | Data Dictionary | P0 | L2 |
| `artifact-document-diagram.runbook-generation` | Runbook Generation | P0 | L2 |
| `artifact-document-diagram.adr-generation` | Adr Generation | P0 | L2 |
| `artifact-document-diagram.c4-context-container-component-diagrams` | C4 Context Container Component Diagrams | P0 | L2 |
| `artifact-document-diagram.er-diagram` | Er Diagram | P0 | L2 |
| `artifact-document-diagram.data-flow-diagram` | Data Flow Diagram | P0 | L2 |
| `artifact-document-diagram.sequence-diagram` | Sequence Diagram | P0 | L2 |
| `artifact-document-diagram.activity-and-flowchart` | Activity And Flowchart | P0 | L2 |
| `artifact-document-diagram.deployment-diagram` | Deployment Diagram | P0 | L2 |
| `artifact-document-diagram.event-topology-diagram` | Event Topology Diagram | P0 | L2 |
| `artifact-document-diagram.mind-map` | Mind Map | P0 | L2 |
| `artifact-document-diagram.project-introduction-presentation` | Project Introduction Presentation | P0 | L2 |
| `artifact-document-diagram.technical-review-presentation` | Technical Review Presentation | P0 | L2 |
| `artifact-document-diagram.executive-summary-report` | Executive Summary Report | P0 | L2 |
| `artifact-document-diagram.project-full-report-bundle` | Project Full Report Bundle | P0 | L2 |
| `artifact-document-diagram.source-evidence-citations` | Source Evidence Citations | P0 | L2 |
| `artifact-document-diagram.artifact-versioning` | Artifact Versioning | P0 | L2 |
| `artifact-document-diagram.human-content-lock` | Human Content Lock | P0 | L2 |
| `artifact-document-diagram.incremental-regeneration` | Incremental Regeneration | P0 | L2 |
| `artifact-document-diagram.stale-artifact-detection` | Stale Artifact Detection | P0 | L2 |
| `artifact-document-diagram.markdown-export` | Markdown Export | P0 | L2 |
| `artifact-document-diagram.html-export` | Html Export | P0 | L2 |
| `artifact-document-diagram.pdf-export` | Pdf Export | P0 | L2 |
| `artifact-document-diagram.docx-export` | Docx Export | P0 | L2 |
| `artifact-document-diagram.pptx-export` | Pptx Export | P0 | L2 |
| `artifact-document-diagram.mermaid-export` | Mermaid Export | P0 | L2 |
| `artifact-document-diagram.plantuml-export` | Plantuml Export | P0 | L2 |
| `artifact-document-diagram.graphviz-export` | Graphviz Export | P0 | L2 |
| `artifact-document-diagram.diagram-render-failure-disclosure` | Diagram Render Failure Disclosure | P0 | L2 |
| `artifact-document-diagram.cross-artifact-consistency` | Cross Artifact Consistency | P0 | L2 |
| `artifact-document-diagram.artifact-access-control` | Artifact Access Control | P0 | L2 |
| `artifact-document-diagram.artifact-digest-and-signature` | Artifact Digest And Signature | P0 | L2 |
| `artifact-document-diagram.artifact-retention-and-deletion` | Artifact Retention And Deletion | P0 | L2 |
| `artifact-document-diagram.diagram-online-edit` | Diagram Online Edit | P1 | L2 |
| `artifact-document-diagram.layout-preservation` | Layout Preservation | P1 | L2 |
| `artifact-document-diagram.manual-node-lock` | Manual Node Lock | P1 | L2 |
| `artifact-document-diagram.template-selection` | Template Selection | P1 | L2 |
| `artifact-document-diagram.brand-theme` | Brand Theme | P1 | L2 |
| `artifact-document-diagram.localization` | Localization | P1 | L2 |
| `artifact-document-diagram.speaker-notes` | Speaker Notes | P1 | L2 |
| `artifact-document-diagram.table-of-contents` | Table Of Contents | P1 | L2 |
| `artifact-document-diagram.deep-links-to-reader` | Deep Links To Reader | P1 | L2 |
| `artifact-document-diagram.embedded-code-snippets` | Embedded Code Snippets | P1 | L2 |
| `artifact-document-diagram.embedded-metrics` | Embedded Metrics | P1 | L2 |
| `artifact-document-diagram.large-diagram-pagination` | Large Diagram Pagination | P1 | L2 |
| `artifact-document-diagram.diagram-diff` | Diagram Diff | P1 | L2 |
| `artifact-document-diagram.document-diff` | Document Diff | P1 | L2 |
| `artifact-document-diagram.presentation-version-diff` | Presentation Version Diff | P1 | L2 |
| `artifact-document-diagram.export-font-fallback` | Export Font Fallback | P1 | L2 |
| `artifact-document-diagram.chart-data-traceability` | Chart Data Traceability | P1 | L2 |
| `artifact-document-diagram.artifact-comment-review` | Artifact Comment Review | P1 | L2 |
| `artifact-document-diagram.approval-before-publish` | Approval Before Publish | P1 | L2 |
| `artifact-document-diagram.git-pr-document-publish` | Git Pr Document Publish | P1 | L2 |
| `artifact-document-diagram.wiki-publish` | Wiki Publish | P1 | L2 |
| `artifact-document-diagram.notion-publish` | Notion Publish | P1 | L2 |
| `artifact-document-diagram.object-storage-publish` | Object Storage Publish | P1 | L2 |
| `artifact-document-diagram.download-expiry-link` | Download Expiry Link | P1 | L2 |
| `artifact-document-diagram.cover-page-customization` | Cover Page Customization | P2 | L1 |
| `artifact-document-diagram.watermark` | Watermark | P2 | L1 |
| `artifact-document-diagram.page-numbering` | Page Numbering | P2 | L1 |
| `artifact-document-diagram.slide-ratio` | Slide Ratio | P2 | L1 |
| `artifact-document-diagram.report-color-theme` | Report Color Theme | P2 | L1 |

## Collaboration, Git, Connectors and Enterprise Integrations (`collaboration-integrations`)

Adapter: `external-collaboration-integration-harness`. Contexts: `github-gitlab-gitee`, `jira-notion`, `slack-teams`, `generic-webhook-mcp`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `collaboration-integrations.project-comment-create-edit-delete` | Project Comment Create Edit Delete | P0 | L2 |
| `collaboration-integrations.mention-and-notification` | Mention And Notification | P0 | L2 |
| `collaboration-integrations.review-request` | Review Request | P0 | L2 |
| `collaboration-integrations.approval-and-rejection` | Approval And Rejection | P0 | L2 |
| `collaboration-integrations.approval-binding-to-artifact-version` | Approval Binding To Artifact Version | P0 | L2 |
| `collaboration-integrations.role-based-comment-and-review-access` | Role Based Comment And Review Access | P0 | L2 |
| `collaboration-integrations.audit-of-collaboration-actions` | Audit Of Collaboration Actions | P0 | L2 |
| `collaboration-integrations.github-app-installation-and-scope` | Github App Installation And Scope | P0 | L2 |
| `collaboration-integrations.gitlab-integration-scope` | Gitlab Integration Scope | P0 | L2 |
| `collaboration-integrations.gitee-integration-scope` | Gitee Integration Scope | P0 | L2 |
| `collaboration-integrations.branch-and-pr-creation` | Branch And Pr Creation | P0 | L2 |
| `collaboration-integrations.commit-status-and-check-run` | Commit Status And Check Run | P0 | L2 |
| `collaboration-integrations.pr-comment-and-review` | Pr Comment And Review | P0 | L2 |
| `collaboration-integrations.merge-protection-respect` | Merge Protection Respect | P0 | L2 |
| `collaboration-integrations.webhook-signature-validation` | Webhook Signature Validation | P0 | L2 |
| `collaboration-integrations.webhook-deduplication-and-order` | Webhook Deduplication And Order | P0 | L2 |
| `collaboration-integrations.connector-oauth-token-broker` | Connector Oauth Token Broker | P0 | L2 |
| `collaboration-integrations.connector-secret-rotation` | Connector Secret Rotation | P0 | L2 |
| `collaboration-integrations.connector-rate-limit-recovery` | Connector Rate Limit Recovery | P0 | L2 |
| `collaboration-integrations.connector-tenant-isolation` | Connector Tenant Isolation | P0 | L2 |
| `collaboration-integrations.mcp-connector-authority` | Mcp Connector Authority | P0 | L2 |
| `collaboration-integrations.jira-issue-create-update-link` | Jira Issue Create Update Link | P0 | L2 |
| `collaboration-integrations.notion-page-create-update` | Notion Page Create Update | P0 | L2 |
| `collaboration-integrations.slack-message-and-thread` | Slack Message And Thread | P0 | L2 |
| `collaboration-integrations.teams-message-and-thread` | Teams Message And Thread | P0 | L2 |
| `collaboration-integrations.inbound-command-authentication` | Inbound Command Authentication | P0 | L2 |
| `collaboration-integrations.outbound-data-redaction` | Outbound Data Redaction | P0 | L2 |
| `collaboration-integrations.connector-failure-and-retry` | Connector Failure And Retry | P0 | L2 |
| `collaboration-integrations.sync-conflict-resolution` | Sync Conflict Resolution | P0 | L2 |
| `collaboration-integrations.connector-audit-trace` | Connector Audit Trace | P0 | L2 |
| `collaboration-integrations.codeowners-review-routing` | Codeowners Review Routing | P1 | L2 |
| `collaboration-integrations.pr-template` | Pr Template | P1 | L2 |
| `collaboration-integrations.release-note-publish` | Release Note Publish | P1 | L2 |
| `collaboration-integrations.wiki-link-back` | Wiki Link Back | P1 | L2 |
| `collaboration-integrations.issue-bidirectional-sync` | Issue Bidirectional Sync | P1 | L2 |
| `collaboration-integrations.status-dashboard-embed` | Status Dashboard Embed | P1 | L2 |
| `collaboration-integrations.calendar-schedule-link` | Calendar Schedule Link | P1 | L2 |
| `collaboration-integrations.email-notification-integration` | Email Notification Integration | P1 | L2 |
| `collaboration-integrations.custom-webhook-transform` | Custom Webhook Transform | P1 | L2 |
| `collaboration-integrations.connector-health-dashboard` | Connector Health Dashboard | P1 | L2 |
| `collaboration-integrations.connector-reconnect` | Connector Reconnect | P1 | L2 |
| `collaboration-integrations.connector-deprecation` | Connector Deprecation | P1 | L2 |
| `collaboration-integrations.bulk-project-migration` | Bulk Project Migration | P1 | L2 |
| `collaboration-integrations.external-id-mapping` | External Id Mapping | P1 | L2 |
| `collaboration-integrations.duplicate-external-resource-prevention` | Duplicate External Resource Prevention | P1 | L2 |
| `collaboration-integrations.integration-data-retention` | Integration Data Retention | P1 | L2 |
| `collaboration-integrations.approval-sla-and-reminder` | Approval Sla And Reminder | P1 | L2 |
| `collaboration-integrations.review-diff-view` | Review Diff View | P1 | L2 |
| `collaboration-integrations.comment-resolution-state` | Comment Resolution State | P1 | L2 |
| `collaboration-integrations.export-collaboration-history` | Export Collaboration History | P1 | L2 |
| `collaboration-integrations.guest-collaborator-restrictions` | Guest Collaborator Restrictions | P1 | L2 |
| `collaboration-integrations.emoji-reaction` | Emoji Reaction | P2 | L1 |
| `collaboration-integrations.comment-pin` | Comment Pin | P2 | L1 |
| `collaboration-integrations.saved-integration-filter` | Saved Integration Filter | P2 | L1 |
| `collaboration-integrations.notification-channel-preference` | Notification Channel Preference | P2 | L1 |
| `collaboration-integrations.integration-logo-metadata` | Integration Logo Metadata | P2 | L1 |

## Billing, Credits, Subscription, Pricing and Entitlements (`billing-entitlements`)

Adapter: `external-billing-ledger-harness`. Contexts: `prepaid-credit`, `subscription`, `per-project-price`, `enterprise-contract`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `billing-entitlements.wallet-create-and-balance` | Wallet Create And Balance | P0 | L2 |
| `billing-entitlements.credit-top-up-posting` | Credit Top Up Posting | P0 | L2 |
| `billing-entitlements.credit-reservation-before-billable-call` | Credit Reservation Before Billable Call | P0 | L2 |
| `billing-entitlements.credit-consumption` | Credit Consumption | P0 | L2 |
| `billing-entitlements.unused-reservation-release` | Unused Reservation Release | P0 | L2 |
| `billing-entitlements.negative-balance-prevention` | Negative Balance Prevention | P0 | L2 |
| `billing-entitlements.concurrent-reservation-no-overspend` | Concurrent Reservation No Overspend | P0 | L2 |
| `billing-entitlements.provider-usage-event-deduplication` | Provider Usage Event Deduplication | P0 | L2 |
| `billing-entitlements.usage-reconciliation` | Usage Reconciliation | P0 | L2 |
| `billing-entitlements.ledger-double-entry` | Ledger Double Entry | P0 | L2 |
| `billing-entitlements.token-input-output-metering` | Token Input Output Metering | P0 | L2 |
| `billing-entitlements.compute-and-storage-metering` | Compute And Storage Metering | P0 | L2 |
| `billing-entitlements.wall-clock-metering` | Wall Clock Metering | P0 | L2 |
| `billing-entitlements.cache-hit-cost-accounting` | Cache Hit Cost Accounting | P0 | L2 |
| `billing-entitlements.retry-and-failed-call-billing-policy` | Retry And Failed Call Billing Policy | P0 | L2 |
| `billing-entitlements.task-cancel-settlement` | Task Cancel Settlement | P0 | L2 |
| `billing-entitlements.subscription-plan-entitlement` | Subscription Plan Entitlement | P0 | L2 |
| `billing-entitlements.plan-limit-enforcement` | Plan Limit Enforcement | P0 | L2 |
| `billing-entitlements.trial-entitlement-and-expiry` | Trial Entitlement And Expiry | P0 | L2 |
| `billing-entitlements.upgrade-downgrade` | Upgrade Downgrade | P0 | L2 |
| `billing-entitlements.proration` | Proration | P0 | L2 |
| `billing-entitlements.price-version-freeze-per-order` | Price Version Freeze Per Order | P0 | L2 |
| `billing-entitlements.project-quote-and-acceptance` | Project Quote And Acceptance | P0 | L2 |
| `billing-entitlements.coupon-and-discount-rules` | Coupon And Discount Rules | P0 | L2 |
| `billing-entitlements.credit-expiration` | Credit Expiration | P0 | L2 |
| `billing-entitlements.refund-credit-adjustment` | Refund Credit Adjustment | P0 | L2 |
| `billing-entitlements.invoice-line-item-consistency` | Invoice Line Item Consistency | P0 | L2 |
| `billing-entitlements.tax-calculation-input-contract` | Tax Calculation Input Contract | P0 | L2 |
| `billing-entitlements.multi-currency-amount-and-rounding` | Multi Currency Amount And Rounding | P0 | L2 |
| `billing-entitlements.billing-webhook-idempotency` | Billing Webhook Idempotency | P0 | L2 |
| `billing-entitlements.billing-access-control` | Billing Access Control | P0 | L2 |
| `billing-entitlements.billing-audit-and-export` | Billing Audit And Export | P0 | L2 |
| `billing-entitlements.financial-period-close-reconciliation` | Financial Period Close Reconciliation | P0 | L2 |
| `billing-entitlements.unexplained-delta-zero` | Unexplained Delta Zero | P0 | L2 |
| `billing-entitlements.usage-threshold-alert` | Usage Threshold Alert | P1 | L2 |
| `billing-entitlements.low-balance-pause-policy` | Low Balance Pause Policy | P1 | L2 |
| `billing-entitlements.auto-recharge-policy` | Auto Recharge Policy | P1 | L2 |
| `billing-entitlements.budget-per-project` | Budget Per Project | P1 | L2 |
| `billing-entitlements.budget-per-tenant` | Budget Per Tenant | P1 | L2 |
| `billing-entitlements.cost-center-tagging` | Cost Center Tagging | P1 | L2 |
| `billing-entitlements.enterprise-commitment-drawdown` | Enterprise Commitment Drawdown | P1 | L2 |
| `billing-entitlements.promotional-credit-priority` | Promotional Credit Priority | P1 | L2 |
| `billing-entitlements.credit-transfer-policy` | Credit Transfer Policy | P1 | L2 |
| `billing-entitlements.invoice-number-sequence` | Invoice Number Sequence | P1 | L2 |
| `billing-entitlements.invoice-pdf-generation` | Invoice Pdf Generation | P1 | L2 |
| `billing-entitlements.statement-generation` | Statement Generation | P1 | L2 |
| `billing-entitlements.billing-portal` | Billing Portal | P1 | L2 |
| `billing-entitlements.payment-method-entitlement-link` | Payment Method Entitlement Link | P1 | L2 |
| `billing-entitlements.plan-feature-matrix` | Plan Feature Matrix | P1 | L2 |
| `billing-entitlements.seat-based-entitlement` | Seat Based Entitlement | P1 | L2 |
| `billing-entitlements.overage-policy` | Overage Policy | P1 | L2 |
| `billing-entitlements.grace-period` | Grace Period | P1 | L2 |
| `billing-entitlements.subscription-renewal` | Subscription Renewal | P1 | L2 |
| `billing-entitlements.failed-renewal-dunning` | Failed Renewal Dunning | P1 | L2 |
| `billing-entitlements.subscription-cancel-at-period-end` | Subscription Cancel At Period End | P1 | L2 |
| `billing-entitlements.billing-data-retention` | Billing Data Retention | P1 | L2 |
| `billing-entitlements.financial-admin-role` | Financial Admin Role | P1 | L2 |
| `billing-entitlements.manual-adjustment-four-eyes` | Manual Adjustment Four Eyes | P1 | L2 |
| `billing-entitlements.chargeback-ledger-adjustment` | Chargeback Ledger Adjustment | P1 | L2 |
| `billing-entitlements.revenue-recognition-export` | Revenue Recognition Export | P1 | L2 |
| `billing-entitlements.pricing-page-display` | Pricing Page Display | P2 | L1 |
| `billing-entitlements.usage-chart` | Usage Chart | P2 | L1 |
| `billing-entitlements.cost-estimate-explanation` | Cost Estimate Explanation | P2 | L1 |
| `billing-entitlements.billing-email-template` | Billing Email Template | P2 | L1 |
| `billing-entitlements.invoice-download-history` | Invoice Download History | P2 | L1 |

## Payment Providers, Refunds, Fraud Controls and Financial Consistency (`payment-finance`)

Adapter: `external-payment-sandbox-harness`. Contexts: `wechat-alipay`, `stripe-paypal-applepay`, `refund-chargeback`, `reconciliation-batch`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `payment-finance.payment-order-create` | Payment Order Create | P0 | L2 |
| `payment-finance.provider-checkout-session` | Provider Checkout Session | P0 | L2 |
| `payment-finance.wechat-pay-callback` | Wechat Pay Callback | P0 | L2 |
| `payment-finance.alipay-callback` | Alipay Callback | P0 | L2 |
| `payment-finance.stripe-webhook` | Stripe Webhook | P0 | L2 |
| `payment-finance.paypal-webhook` | Paypal Webhook | P0 | L2 |
| `payment-finance.apple-pay-token-flow` | Apple Pay Token Flow | P0 | L2 |
| `payment-finance.callback-signature-verification` | Callback Signature Verification | P0 | L2 |
| `payment-finance.callback-replay-defense` | Callback Replay Defense | P0 | L2 |
| `payment-finance.duplicate-callback-idempotency` | Duplicate Callback Idempotency | P0 | L2 |
| `payment-finance.out-of-order-callback` | Out Of Order Callback | P0 | L2 |
| `payment-finance.payment-pending-success-failure-state-machine` | Payment Pending Success Failure State Machine | P0 | L2 |
| `payment-finance.timeout-and-late-success` | Timeout And Late Success | P0 | L2 |
| `payment-finance.provider-query-reconciliation` | Provider Query Reconciliation | P0 | L2 |
| `payment-finance.ledger-posting-after-confirmed-payment` | Ledger Posting After Confirmed Payment | P0 | L2 |
| `payment-finance.no-credit-before-payment-confirmation` | No Credit Before Payment Confirmation | P0 | L2 |
| `payment-finance.full-refund` | Full Refund | P0 | L2 |
| `payment-finance.partial-refund` | Partial Refund | P0 | L2 |
| `payment-finance.duplicate-refund-defense` | Duplicate Refund Defense | P0 | L2 |
| `payment-finance.refund-after-settlement` | Refund After Settlement | P0 | L2 |
| `payment-finance.refund-ledger-consistency` | Refund Ledger Consistency | P0 | L2 |
| `payment-finance.chargeback-and-dispute-state` | Chargeback And Dispute State | P0 | L2 |
| `payment-finance.payment-order-expiry` | Payment Order Expiry | P0 | L2 |
| `payment-finance.amount-currency-order-binding` | Amount Currency Order Binding | P0 | L2 |
| `payment-finance.provider-account-tenant-binding` | Provider Account Tenant Binding | P0 | L2 |
| `payment-finance.webhook-secret-rotation` | Webhook Secret Rotation | P0 | L2 |
| `payment-finance.payment-data-redaction` | Payment Data Redaction | P0 | L2 |
| `payment-finance.card-data-non-storage` | Card Data Non Storage | P0 | L2 |
| `payment-finance.tokenization-boundary` | Tokenization Boundary | P0 | L2 |
| `payment-finance.anti-phishing-redirect-domain` | Anti Phishing Redirect Domain | P0 | L2 |
| `payment-finance.fraud-risk-block-and-review` | Fraud Risk Block And Review | P0 | L2 |
| `payment-finance.financial-audit-trail` | Financial Audit Trail | P0 | L2 |
| `payment-finance.daily-provider-ledger-reconciliation` | Daily Provider Ledger Reconciliation | P0 | L2 |
| `payment-finance.settlement-file-import` | Settlement File Import | P0 | L2 |
| `payment-finance.unmatched-transaction-quarantine` | Unmatched Transaction Quarantine | P0 | L2 |
| `payment-finance.manual-resolution-four-eyes` | Manual Resolution Four Eyes | P0 | L2 |
| `payment-finance.multi-currency-fx-rate-freeze` | Multi Currency Fx Rate Freeze | P1 | L2 |
| `payment-finance.provider-fee-accounting` | Provider Fee Accounting | P1 | L2 |
| `payment-finance.settlement-delay` | Settlement Delay | P1 | L2 |
| `payment-finance.payout-status` | Payout Status | P1 | L2 |
| `payment-finance.payment-method-update` | Payment Method Update | P1 | L2 |
| `payment-finance.saved-payment-token-policy` | Saved Payment Token Policy | P1 | L2 |
| `payment-finance.3ds-or-step-up-flow` | 3Ds Or Step Up Flow | P1 | L2 |
| `payment-finance.risk-rule-versioning` | Risk Rule Versioning | P1 | L2 |
| `payment-finance.refund-sla` | Refund Sla | P1 | L2 |
| `payment-finance.dispute-evidence-package` | Dispute Evidence Package | P1 | L2 |
| `payment-finance.invoice-receipt-link` | Invoice Receipt Link | P1 | L2 |
| `payment-finance.payment-provider-failover-policy` | Payment Provider Failover Policy | P1 | L2 |
| `payment-finance.domestic-international-routing` | Domestic International Routing | P1 | L2 |
| `payment-finance.sandbox-production-key-separation` | Sandbox Production Key Separation | P1 | L2 |
| `payment-finance.provider-rate-limit-recovery` | Provider Rate Limit Recovery | P1 | L2 |
| `payment-finance.provider-maintenance-window` | Provider Maintenance Window | P1 | L2 |
| `payment-finance.payment-notification` | Payment Notification | P1 | L2 |
| `payment-finance.failed-payment-retry` | Failed Payment Retry | P1 | L2 |
| `payment-finance.idempotency-key-expiry` | Idempotency Key Expiry | P1 | L2 |
| `payment-finance.merchant-order-search` | Merchant Order Search | P1 | L2 |
| `payment-finance.financial-export` | Financial Export | P1 | L2 |
| `payment-finance.payment-method-logo-display` | Payment Method Logo Display | P2 | L1 |
| `payment-finance.checkout-localization` | Checkout Localization | P2 | L1 |
| `payment-finance.receipt-email` | Receipt Email | P2 | L1 |
| `payment-finance.payment-history-filter` | Payment History Filter | P2 | L1 |
| `payment-finance.refund-status-ui` | Refund Status Ui | P2 | L1 |

## Public APIs, SDKs, CLI, Streaming and Webhooks (`api-sdk-webhook`)

Adapter: `external-api-sdk-harness`. Contexts: `rest-api`, `async-event`, `webhook`, `sdk-cli`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `api-sdk-webhook.openapi-schema-validity` | Openapi Schema Validity | P0 | L2 |
| `api-sdk-webhook.api-authentication` | Api Authentication | P0 | L2 |
| `api-sdk-webhook.api-authorization` | Api Authorization | P0 | L2 |
| `api-sdk-webhook.request-validation` | Request Validation | P0 | L2 |
| `api-sdk-webhook.consistent-error-model` | Consistent Error Model | P0 | L2 |
| `api-sdk-webhook.idempotent-create` | Idempotent Create | P0 | L2 |
| `api-sdk-webhook.pagination-cursor-and-stability` | Pagination Cursor And Stability | P0 | L2 |
| `api-sdk-webhook.filter-sort-search` | Filter Sort Search | P0 | L2 |
| `api-sdk-webhook.etag-and-optimistic-concurrency` | Etag And Optimistic Concurrency | P0 | L2 |
| `api-sdk-webhook.rate-limit-headers-and-enforcement` | Rate Limit Headers And Enforcement | P0 | L2 |
| `api-sdk-webhook.request-id-correlation` | Request Id Correlation | P0 | L2 |
| `api-sdk-webhook.api-versioning` | Api Versioning | P0 | L2 |
| `api-sdk-webhook.backward-compatible-change` | Backward Compatible Change | P0 | L2 |
| `api-sdk-webhook.breaking-change-detection` | Breaking Change Detection | P0 | L2 |
| `api-sdk-webhook.deprecation-and-sunset` | Deprecation And Sunset | P0 | L2 |
| `api-sdk-webhook.long-running-operation-resource` | Long Running Operation Resource | P0 | L2 |
| `api-sdk-webhook.task-progress-sse` | Task Progress Sse | P0 | L2 |
| `api-sdk-webhook.websocket-reconnect-and-order` | Websocket Reconnect And Order | P0 | L2 |
| `api-sdk-webhook.file-upload-download-integrity` | File Upload Download Integrity | P0 | L2 |
| `api-sdk-webhook.multipart-resume` | Multipart Resume | P0 | L2 |
| `api-sdk-webhook.webhook-registration` | Webhook Registration | P0 | L2 |
| `api-sdk-webhook.webhook-signature` | Webhook Signature | P0 | L2 |
| `api-sdk-webhook.webhook-retry-backoff` | Webhook Retry Backoff | P0 | L2 |
| `api-sdk-webhook.webhook-deduplication` | Webhook Deduplication | P0 | L2 |
| `api-sdk-webhook.webhook-ordering-and-causal-id` | Webhook Ordering And Causal Id | P0 | L2 |
| `api-sdk-webhook.webhook-disable-after-failure-policy` | Webhook Disable After Failure Policy | P0 | L2 |
| `api-sdk-webhook.asyncapi-contract` | Asyncapi Contract | P0 | L2 |
| `api-sdk-webhook.event-schema-versioning` | Event Schema Versioning | P0 | L2 |
| `api-sdk-webhook.event-consumer-idempotency` | Event Consumer Idempotency | P0 | L2 |
| `api-sdk-webhook.sdk-auth-and-retry` | Sdk Auth And Retry | P0 | L2 |
| `api-sdk-webhook.sdk-pagination` | Sdk Pagination | P0 | L2 |
| `api-sdk-webhook.sdk-long-running-operations` | Sdk Long Running Operations | P0 | L2 |
| `api-sdk-webhook.cli-auth-profile` | Cli Auth Profile | P0 | L2 |
| `api-sdk-webhook.cli-noninteractive-json-output` | Cli Noninteractive Json Output | P0 | L2 |
| `api-sdk-webhook.cli-exit-code-and-errors` | Cli Exit Code And Errors | P0 | L2 |
| `api-sdk-webhook.cli-resume-and-cancel` | Cli Resume And Cancel | P0 | L2 |
| `api-sdk-webhook.java-sdk-conformance` | Java Sdk Conformance | P1 | L2 |
| `api-sdk-webhook.python-sdk-conformance` | Python Sdk Conformance | P1 | L2 |
| `api-sdk-webhook.go-sdk-conformance` | Go Sdk Conformance | P1 | L2 |
| `api-sdk-webhook.typescript-sdk-conformance` | Typescript Sdk Conformance | P1 | L2 |
| `api-sdk-webhook.csharp-sdk-conformance` | Csharp Sdk Conformance | P1 | L2 |
| `api-sdk-webhook.sdk-generated-code-reproducibility` | Sdk Generated Code Reproducibility | P1 | L2 |
| `api-sdk-webhook.sdk-semver` | Sdk Semver | P1 | L2 |
| `api-sdk-webhook.sdk-proxy-and-timeout` | Sdk Proxy And Timeout | P1 | L2 |
| `api-sdk-webhook.sdk-streaming` | Sdk Streaming | P1 | L2 |
| `api-sdk-webhook.sdk-upload-download` | Sdk Upload Download | P1 | L2 |
| `api-sdk-webhook.graphql-contract` | Graphql Contract | P1 | L2 |
| `api-sdk-webhook.grpc-contract` | Grpc Contract | P1 | L2 |
| `api-sdk-webhook.grpc-streaming` | Grpc Streaming | P1 | L2 |
| `api-sdk-webhook.api-batch-endpoint` | Api Batch Endpoint | P1 | L2 |
| `api-sdk-webhook.api-field-selection` | Api Field Selection | P1 | L2 |
| `api-sdk-webhook.api-compression` | Api Compression | P1 | L2 |
| `api-sdk-webhook.webhook-payload-redaction` | Webhook Payload Redaction | P1 | L2 |
| `api-sdk-webhook.webhook-test-delivery` | Webhook Test Delivery | P1 | L2 |
| `api-sdk-webhook.sandbox-api-environment` | Sandbox Api Environment | P1 | L2 |
| `api-sdk-webhook.api-changelog` | Api Changelog | P1 | L2 |
| `api-sdk-webhook.api-documentation-code-samples` | Api Documentation Code Samples | P1 | L2 |
| `api-sdk-webhook.api-explorer` | Api Explorer | P2 | L1 |
| `api-sdk-webhook.sdk-install-snippets` | Sdk Install Snippets | P2 | L1 |
| `api-sdk-webhook.cli-shell-completion` | Cli Shell Completion | P2 | L1 |
| `api-sdk-webhook.webhook-delivery-dashboard` | Webhook Delivery Dashboard | P2 | L1 |
| `api-sdk-webhook.api-usage-dashboard` | Api Usage Dashboard | P2 | L1 |

## Durable Storage, Object Artifacts, Search and Cache (`storage-search-cache`)

Adapter: `external-storage-search-cache-harness`. Contexts: `postgresql`, `object-storage`, `search-index`, `redis-cache`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `storage-search-cache.postgresql-is-source-of-truth` | Postgresql Is Source Of Truth | P0 | L2 |
| `storage-search-cache.schema-migration-forward` | Schema Migration Forward | P0 | L2 |
| `storage-search-cache.schema-migration-rollback-or-compensation` | Schema Migration Rollback Or Compensation | P0 | L2 |
| `storage-search-cache.row-level-security` | Row Level Security | P0 | L2 |
| `storage-search-cache.tenant-partition-key` | Tenant Partition Key | P0 | L2 |
| `storage-search-cache.transaction-isolation-and-locking` | Transaction Isolation And Locking | P0 | L2 |
| `storage-search-cache.idempotency-unique-constraint` | Idempotency Unique Constraint | P0 | L2 |
| `storage-search-cache.outbox-same-transaction` | Outbox Same Transaction | P0 | L2 |
| `storage-search-cache.database-failover` | Database Failover | P0 | L2 |
| `storage-search-cache.connection-pool-exhaustion` | Connection Pool Exhaustion | P0 | L2 |
| `storage-search-cache.backup-and-restore` | Backup And Restore | P0 | L2 |
| `storage-search-cache.point-in-time-recovery` | Point In Time Recovery | P0 | L2 |
| `storage-search-cache.data-retention-and-purge` | Data Retention And Purge | P0 | L2 |
| `storage-search-cache.legal-hold` | Legal Hold | P0 | L2 |
| `storage-search-cache.encryption-at-rest-and-in-transit` | Encryption At Rest And In Transit | P0 | L2 |
| `storage-search-cache.key-rotation` | Key Rotation | P0 | L2 |
| `storage-search-cache.object-content-addressed-storage` | Object Content Addressed Storage | P0 | L2 |
| `storage-search-cache.object-digest-verification` | Object Digest Verification | P0 | L2 |
| `storage-search-cache.multipart-upload-resume` | Multipart Upload Resume | P0 | L2 |
| `storage-search-cache.partial-upload-cleanup` | Partial Upload Cleanup | P0 | L2 |
| `storage-search-cache.worm-evidence-storage` | Worm Evidence Storage | P0 | L2 |
| `storage-search-cache.artifact-access-control` | Artifact Access Control | P0 | L2 |
| `storage-search-cache.artifact-lifecycle-and-gc` | Artifact Lifecycle And Gc | P0 | L2 |
| `storage-search-cache.search-index-build` | Search Index Build | P0 | L2 |
| `storage-search-cache.search-index-incremental-update` | Search Index Incremental Update | P0 | L2 |
| `storage-search-cache.search-index-cutover` | Search Index Cutover | P0 | L2 |
| `storage-search-cache.search-tenant-filter` | Search Tenant Filter | P0 | L2 |
| `storage-search-cache.search-deletion-purge` | Search Deletion Purge | P0 | L2 |
| `storage-search-cache.cache-key-candidate-model-skill-tenant-binding` | Cache Key Candidate Model Skill Tenant Binding | P0 | L2 |
| `storage-search-cache.cache-ttl-and-eviction` | Cache Ttl And Eviction | P0 | L2 |
| `storage-search-cache.cache-poisoning-defense` | Cache Poisoning Defense | P0 | L2 |
| `storage-search-cache.stale-cache-invalidation` | Stale Cache Invalidation | P0 | L2 |
| `storage-search-cache.redis-flush-no-durable-loss` | Redis Flush No Durable Loss | P0 | L2 |
| `storage-search-cache.cache-stampede-protection` | Cache Stampede Protection | P0 | L2 |
| `storage-search-cache.cross-tenant-cache-denial` | Cross Tenant Cache Denial | P0 | L2 |
| `storage-search-cache.storage-quota-enforcement` | Storage Quota Enforcement | P0 | L2 |
| `storage-search-cache.table-partitioning` | Table Partitioning | P1 | L2 |
| `storage-search-cache.archive-tier` | Archive Tier | P1 | L2 |
| `storage-search-cache.database-read-replica-consistency` | Database Read Replica Consistency | P1 | L2 |
| `storage-search-cache.cross-region-replication` | Cross Region Replication | P1 | L2 |
| `storage-search-cache.object-deduplication` | Object Deduplication | P1 | L2 |
| `storage-search-cache.object-versioning` | Object Versioning | P1 | L2 |
| `storage-search-cache.artifact-expiring-link` | Artifact Expiring Link | P1 | L2 |
| `storage-search-cache.search-ranking-relevance` | Search Ranking Relevance | P1 | L2 |
| `storage-search-cache.search-synonym-and-tokenization` | Search Synonym And Tokenization | P1 | L2 |
| `storage-search-cache.search-cjk-support` | Search Cjk Support | P1 | L2 |
| `storage-search-cache.search-large-result-pagination` | Search Large Result Pagination | P1 | L2 |
| `storage-search-cache.cache-warmup` | Cache Warmup | P1 | L2 |
| `storage-search-cache.negative-cache-policy` | Negative Cache Policy | P1 | L2 |
| `storage-search-cache.distributed-lock-expiry` | Distributed Lock Expiry | P1 | L2 |
| `storage-search-cache.blob-metadata-index` | Blob Metadata Index | P1 | L2 |
| `storage-search-cache.orphan-blob-scan` | Orphan Blob Scan | P1 | L2 |
| `storage-search-cache.checksum-scrub` | Checksum Scrub | P1 | L2 |
| `storage-search-cache.backup-encryption` | Backup Encryption | P1 | L2 |
| `storage-search-cache.restore-drill` | Restore Drill | P1 | L2 |
| `storage-search-cache.database-statistics-and-vacuum` | Database Statistics And Vacuum | P1 | L2 |
| `storage-search-cache.storage-cost-report` | Storage Cost Report | P1 | L2 |
| `storage-search-cache.retention-policy-preview` | Retention Policy Preview | P1 | L2 |
| `storage-search-cache.storage-usage-dashboard` | Storage Usage Dashboard | P2 | L1 |
| `storage-search-cache.cache-hit-dashboard` | Cache Hit Dashboard | P2 | L1 |
| `storage-search-cache.search-index-status` | Search Index Status | P2 | L1 |
| `storage-search-cache.backup-history-ui` | Backup History Ui | P2 | L1 |
| `storage-search-cache.artifact-browser` | Artifact Browser | P2 | L1 |

## Deployment, Kubernetes, Private Cloud, Observability and Disaster Recovery (`deployment-operations`)

Adapter: `external-deployment-chaos-harness`. Contexts: `saas`, `private-cloud`, `air-gapped`, `multi-region`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `deployment-operations.docker-image-build` | Docker Image Build | P0 | L2 |
| `deployment-operations.immutable-image-digest` | Immutable Image Digest | P0 | L2 |
| `deployment-operations.sbom-and-provenance` | Sbom And Provenance | P0 | L2 |
| `deployment-operations.container-nonroot-and-readonly` | Container Nonroot And Readonly | P0 | L2 |
| `deployment-operations.docker-compose-install` | Docker Compose Install | P0 | L2 |
| `deployment-operations.kubernetes-manifest-and-helm` | Kubernetes Manifest And Helm | P0 | L2 |
| `deployment-operations.namespace-and-service-account-isolation` | Namespace And Service Account Isolation | P0 | L2 |
| `deployment-operations.network-policy-deny-by-default` | Network Policy Deny By Default | P0 | L2 |
| `deployment-operations.secret-injection` | Secret Injection | P0 | L2 |
| `deployment-operations.config-versioning` | Config Versioning | P0 | L2 |
| `deployment-operations.database-migration-job` | Database Migration Job | P0 | L2 |
| `deployment-operations.rolling-upgrade` | Rolling Upgrade | P0 | L2 |
| `deployment-operations.blue-green-deployment` | Blue Green Deployment | P0 | L2 |
| `deployment-operations.canary-deployment` | Canary Deployment | P0 | L2 |
| `deployment-operations.rollback` | Rollback | P0 | L2 |
| `deployment-operations.livez` | Livez | P0 | L2 |
| `deployment-operations.readyz` | Readyz | P0 | L2 |
| `deployment-operations.metrics` | Metrics | P0 | L2 |
| `deployment-operations.version-endpoint` | Version Endpoint | P0 | L2 |
| `deployment-operations.structured-logs` | Structured Logs | P0 | L2 |
| `deployment-operations.distributed-traces` | Distributed Traces | P0 | L2 |
| `deployment-operations.otel-semantic-conventions` | Otel Semantic Conventions | P0 | L2 |
| `deployment-operations.slo-and-error-budget` | Slo And Error Budget | P0 | L2 |
| `deployment-operations.alert-routing` | Alert Routing | P0 | L2 |
| `deployment-operations.incident-runbook` | Incident Runbook | P0 | L2 |
| `deployment-operations.horizontal-autoscaling` | Horizontal Autoscaling | P0 | L2 |
| `deployment-operations.queue-worker-autoscaling` | Queue Worker Autoscaling | P0 | L2 |
| `deployment-operations.capacity-and-backpressure` | Capacity And Backpressure | P0 | L2 |
| `deployment-operations.graceful-shutdown` | Graceful Shutdown | P0 | L2 |
| `deployment-operations.drain-and-requeue` | Drain And Requeue | P0 | L2 |
| `deployment-operations.node-loss-recovery` | Node Loss Recovery | P0 | L2 |
| `deployment-operations.multi-zone-failure` | Multi Zone Failure | P0 | L2 |
| `deployment-operations.database-disaster-recovery` | Database Disaster Recovery | P0 | L2 |
| `deployment-operations.object-storage-disaster-recovery` | Object Storage Disaster Recovery | P0 | L2 |
| `deployment-operations.rpo-rto-evidence` | Rpo Rto Evidence | P0 | L2 |
| `deployment-operations.backup-restore-drill` | Backup Restore Drill | P0 | L2 |
| `deployment-operations.private-cloud-install-upgrade` | Private Cloud Install Upgrade | P0 | L2 |
| `deployment-operations.air-gapped-dependency-bundle` | Air Gapped Dependency Bundle | P0 | L2 |
| `deployment-operations.license-and-entitlement-offline` | License And Entitlement Offline | P0 | L2 |
| `deployment-operations.support-diagnostic-bundle` | Support Diagnostic Bundle | P0 | L2 |
| `deployment-operations.production-secret-no-placeholder` | Production Secret No Placeholder | P0 | L2 |
| `deployment-operations.terraform-or-infrastructure-as-code` | Terraform Or Infrastructure As Code | P1 | L2 |
| `deployment-operations.gitops-deployment` | Gitops Deployment | P1 | L2 |
| `deployment-operations.policy-as-code-admission` | Policy As Code Admission | P1 | L2 |
| `deployment-operations.image-vulnerability-gate` | Image Vulnerability Gate | P1 | L2 |
| `deployment-operations.runtime-security-monitoring` | Runtime Security Monitoring | P1 | L2 |
| `deployment-operations.multi-region-active-passive` | Multi Region Active Passive | P1 | L2 |
| `deployment-operations.multi-region-failover` | Multi Region Failover | P1 | L2 |
| `deployment-operations.regional-data-residency` | Regional Data Residency | P1 | L2 |
| `deployment-operations.maintenance-window` | Maintenance Window | P1 | L2 |
| `deployment-operations.zero-downtime-schema-evolution` | Zero Downtime Schema Evolution | P1 | L2 |
| `deployment-operations.load-test-and-soak` | Load Test And Soak | P1 | L2 |
| `deployment-operations.memory-thread-fd-leak` | Memory Thread Fd Leak | P1 | L2 |
| `deployment-operations.cost-capacity-model` | Cost Capacity Model | P1 | L2 |
| `deployment-operations.autoscaling-thrash-defense` | Autoscaling Thrash Defense | P1 | L2 |
| `deployment-operations.chaos-network-latency-loss` | Chaos Network Latency Loss | P1 | L2 |
| `deployment-operations.dependency-outage-fallback` | Dependency Outage Fallback | P1 | L2 |
| `deployment-operations.provider-outage-fallback` | Provider Outage Fallback | P1 | L2 |
| `deployment-operations.observability-backend-outage` | Observability Backend Outage | P1 | L2 |
| `deployment-operations.log-cardinality-control` | Log Cardinality Control | P1 | L2 |
| `deployment-operations.metric-cardinality-control` | Metric Cardinality Control | P1 | L2 |
| `deployment-operations.trace-sampling-policy` | Trace Sampling Policy | P1 | L2 |
| `deployment-operations.runbook-automation` | Runbook Automation | P1 | L2 |
| `deployment-operations.incident-postmortem-link` | Incident Postmortem Link | P1 | L2 |
| `deployment-operations.upgrade-compatibility-matrix` | Upgrade Compatibility Matrix | P1 | L2 |
| `deployment-operations.uninstall-and-data-retention` | Uninstall And Data Retention | P1 | L2 |
| `deployment-operations.deployment-progress-ui` | Deployment Progress Ui | P2 | L1 |
| `deployment-operations.cluster-status-ui` | Cluster Status Ui | P2 | L1 |
| `deployment-operations.version-changelog-ui` | Version Changelog Ui | P2 | L1 |
| `deployment-operations.maintenance-banner` | Maintenance Banner | P2 | L1 |
| `deployment-operations.support-log-download` | Support Log Download | P2 | L1 |

## Application, AI, Agentic, Supply-Chain, Privacy and Compliance Assurance (`security-privacy-compliance`)

Adapter: `external-security-compliance-harness`. Contexts: `web-and-api`, `agentic-ai`, `repository-supply-chain`, `mobile-or-miniapp`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `security-privacy-compliance.threat-model-and-asset-boundary` | Threat Model And Asset Boundary | P0 | L2 |
| `security-privacy-compliance.secure-default-configuration` | Secure Default Configuration | P0 | L2 |
| `security-privacy-compliance.authentication-security` | Authentication Security | P0 | L2 |
| `security-privacy-compliance.authorization-security` | Authorization Security | P0 | L2 |
| `security-privacy-compliance.session-security` | Session Security | P0 | L2 |
| `security-privacy-compliance.input-validation-and-output-encoding` | Input Validation And Output Encoding | P0 | L2 |
| `security-privacy-compliance.sql-command-template-injection` | Sql Command Template Injection | P0 | L2 |
| `security-privacy-compliance.xss` | Xss | P0 | L2 |
| `security-privacy-compliance.csrf` | Csrf | P0 | L2 |
| `security-privacy-compliance.ssrf` | Ssrf | P0 | L2 |
| `security-privacy-compliance.path-traversal` | Path Traversal | P0 | L2 |
| `security-privacy-compliance.unsafe-deserialization` | Unsafe Deserialization | P0 | L2 |
| `security-privacy-compliance.file-upload-security` | File Upload Security | P0 | L2 |
| `security-privacy-compliance.cryptography-and-key-management` | Cryptography And Key Management | P0 | L2 |
| `security-privacy-compliance.secret-management` | Secret Management | P0 | L2 |
| `security-privacy-compliance.security-logging-and-monitoring` | Security Logging And Monitoring | P0 | L2 |
| `security-privacy-compliance.error-and-exception-data-leakage` | Error And Exception Data Leakage | P0 | L2 |
| `security-privacy-compliance.dos-and-resource-exhaustion` | Dos And Resource Exhaustion | P0 | L2 |
| `security-privacy-compliance.sandbox-escape-defense` | Sandbox Escape Defense | P0 | L2 |
| `security-privacy-compliance.malicious-repository-build-defense` | Malicious Repository Build Defense | P0 | L2 |
| `security-privacy-compliance.dependency-confusion-and-typosquat` | Dependency Confusion And Typosquat | P0 | L2 |
| `security-privacy-compliance.vulnerability-scan-and-policy` | Vulnerability Scan And Policy | P0 | L2 |
| `security-privacy-compliance.sbom-vex` | Sbom Vex | P0 | L2 |
| `security-privacy-compliance.slsa-source-build-provenance` | Slsa Source Build Provenance | P0 | L2 |
| `security-privacy-compliance.artifact-signature-and-admission` | Artifact Signature And Admission | P0 | L2 |
| `security-privacy-compliance.license-policy` | License Policy | P0 | L2 |
| `security-privacy-compliance.prompt-injection-direct` | Prompt Injection Direct | P0 | L2 |
| `security-privacy-compliance.prompt-injection-indirect` | Prompt Injection Indirect | P0 | L2 |
| `security-privacy-compliance.sensitive-information-disclosure` | Sensitive Information Disclosure | P0 | L2 |
| `security-privacy-compliance.excessive-agency` | Excessive Agency | P0 | L2 |
| `security-privacy-compliance.tool-misuse` | Tool Misuse | P0 | L2 |
| `security-privacy-compliance.insecure-output-handling` | Insecure Output Handling | P0 | L2 |
| `security-privacy-compliance.model-denial-of-service` | Model Denial Of Service | P0 | L2 |
| `security-privacy-compliance.model-or-data-poisoning` | Model Or Data Poisoning | P0 | L2 |
| `security-privacy-compliance.rag-poisoning` | Rag Poisoning | P0 | L2 |
| `security-privacy-compliance.agent-identity-and-delegation` | Agent Identity And Delegation | P0 | L2 |
| `security-privacy-compliance.agent-memory-manipulation` | Agent Memory Manipulation | P0 | L2 |
| `security-privacy-compliance.agent-human-approval-bypass` | Agent Human Approval Bypass | P0 | L2 |
| `security-privacy-compliance.cross-tenant-ai-data-leakage` | Cross Tenant Ai Data Leakage | P0 | L2 |
| `security-privacy-compliance.pii-classification-and-minimization` | Pii Classification And Minimization | P0 | L2 |
| `security-privacy-compliance.consent-and-purpose-limitation` | Consent And Purpose Limitation | P0 | L2 |
| `security-privacy-compliance.data-access-export-delete` | Data Access Export Delete | P0 | L2 |
| `security-privacy-compliance.retention-and-legal-hold` | Retention And Legal Hold | P0 | L2 |
| `security-privacy-compliance.data-residency` | Data Residency | P0 | L2 |
| `security-privacy-compliance.encryption-and-key-rotation` | Encryption And Key Rotation | P0 | L2 |
| `security-privacy-compliance.audit-evidence-immutability` | Audit Evidence Immutability | P0 | L2 |
| `security-privacy-compliance.security-incident-response` | Security Incident Response | P0 | L2 |
| `security-privacy-compliance.penetration-and-red-team-regression` | Penetration And Red Team Regression | P0 | L2 |
| `security-privacy-compliance.privileged-access-review` | Privileged Access Review | P0 | L2 |
| `security-privacy-compliance.security-header-policy` | Security Header Policy | P1 | L2 |
| `security-privacy-compliance.csp` | Csp | P1 | L2 |
| `security-privacy-compliance.cors` | Cors | P1 | L2 |
| `security-privacy-compliance.clickjacking-defense` | Clickjacking Defense | P1 | L2 |
| `security-privacy-compliance.open-redirect` | Open Redirect | P1 | L2 |
| `security-privacy-compliance.http-request-smuggling-boundary` | Http Request Smuggling Boundary | P1 | L2 |
| `security-privacy-compliance.dns-rebinding-boundary` | Dns Rebinding Boundary | P1 | L2 |
| `security-privacy-compliance.mobile-secure-storage` | Mobile Secure Storage | P1 | L2 |
| `security-privacy-compliance.mobile-auth-and-biometric` | Mobile Auth And Biometric | P1 | L2 |
| `security-privacy-compliance.mobile-network-security` | Mobile Network Security | P1 | L2 |
| `security-privacy-compliance.mobile-platform-interaction` | Mobile Platform Interaction | P1 | L2 |
| `security-privacy-compliance.mobile-code-quality-and-resilience` | Mobile Code Quality And Resilience | P1 | L2 |
| `security-privacy-compliance.privacy-impact-assessment` | Privacy Impact Assessment | P1 | L2 |
| `security-privacy-compliance.data-processing-inventory` | Data Processing Inventory | P1 | L2 |
| `security-privacy-compliance.subprocessor-registry` | Subprocessor Registry | P1 | L2 |
| `security-privacy-compliance.regional-legal-policy-profile` | Regional Legal Policy Profile | P1 | L2 |
| `security-privacy-compliance.security-control-waiver-expiry` | Security Control Waiver Expiry | P1 | L2 |
| `security-privacy-compliance.psirt-vulnerability-intake` | Psirt Vulnerability Intake | P1 | L2 |
| `security-privacy-compliance.cvss-and-exploitability-triage` | Cvss And Exploitability Triage | P1 | L2 |
| `security-privacy-compliance.patch-sla` | Patch Sla | P1 | L2 |
| `security-privacy-compliance.security-training-evidence` | Security Training Evidence | P1 | L2 |
| `security-privacy-compliance.independent-evidence-review` | Independent Evidence Review | P1 | L2 |
| `security-privacy-compliance.abuse-rate-limit` | Abuse Rate Limit | P1 | L2 |
| `security-privacy-compliance.fraud-anomaly-monitor` | Fraud Anomaly Monitor | P1 | L2 |
| `security-privacy-compliance.account-takeover-detection` | Account Takeover Detection | P1 | L2 |
| `security-privacy-compliance.bot-defense` | Bot Defense | P1 | L2 |
| `security-privacy-compliance.secure-support-impersonation` | Secure Support Impersonation | P1 | L2 |
| `security-privacy-compliance.security-dashboard` | Security Dashboard | P2 | L1 |
| `security-privacy-compliance.privacy-center` | Privacy Center | P2 | L1 |
| `security-privacy-compliance.audit-export-ui` | Audit Export Ui | P2 | L1 |
| `security-privacy-compliance.vulnerability-status-ui` | Vulnerability Status Ui | P2 | L1 |
| `security-privacy-compliance.security-guidance-links` | Security Guidance Links | P2 | L1 |

## Web User Experience, Accessibility, Responsive Design and Localization (`ui-accessibility-localization`)

Adapter: `external-ui-accessibility-harness`. Contexts: `desktop-web`, `mobile-web`, `keyboard-screen-reader`, `multilingual`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `ui-accessibility-localization.critical-user-flow-e2e` | Critical User Flow E2E | P0 | L2 |
| `ui-accessibility-localization.route-authorization` | Route Authorization | P0 | L2 |
| `ui-accessibility-localization.form-validation-and-errors` | Form Validation And Errors | P0 | L2 |
| `ui-accessibility-localization.loading-empty-error-success-states` | Loading Empty Error Success States | P0 | L2 |
| `ui-accessibility-localization.unsaved-change-protection` | Unsaved Change Protection | P0 | L2 |
| `ui-accessibility-localization.responsive-layout` | Responsive Layout | P0 | L2 |
| `ui-accessibility-localization.keyboard-navigation` | Keyboard Navigation | P0 | L2 |
| `ui-accessibility-localization.visible-focus` | Visible Focus | P0 | L2 |
| `ui-accessibility-localization.screen-reader-name-role-state` | Screen Reader Name Role State | P0 | L2 |
| `ui-accessibility-localization.semantic-headings-and-landmarks` | Semantic Headings And Landmarks | P0 | L2 |
| `ui-accessibility-localization.form-labels-and-instructions` | Form Labels And Instructions | P0 | L2 |
| `ui-accessibility-localization.color-contrast` | Color Contrast | P0 | L2 |
| `ui-accessibility-localization.non-color-status-cues` | Non Color Status Cues | P0 | L2 |
| `ui-accessibility-localization.zoom-and-reflow` | Zoom And Reflow | P0 | L2 |
| `ui-accessibility-localization.reduced-motion` | Reduced Motion | P0 | L2 |
| `ui-accessibility-localization.timeout-extension` | Timeout Extension | P0 | L2 |
| `ui-accessibility-localization.accessible-modal-and-dialog` | Accessible Modal And Dialog | P0 | L2 |
| `ui-accessibility-localization.drag-drop-keyboard-alternative` | Drag Drop Keyboard Alternative | P0 | L2 |
| `ui-accessibility-localization.table-grid-accessibility` | Table Grid Accessibility | P0 | L2 |
| `ui-accessibility-localization.live-region-for-progress` | Live Region For Progress | P0 | L2 |
| `ui-accessibility-localization.error-summary-and-focus` | Error Summary And Focus | P0 | L2 |
| `ui-accessibility-localization.file-upload-accessibility` | File Upload Accessibility | P0 | L2 |
| `ui-accessibility-localization.english-localization` | English Localization | P0 | L2 |
| `ui-accessibility-localization.simplified-chinese-localization` | Simplified Chinese Localization | P0 | L2 |
| `ui-accessibility-localization.japanese-localization` | Japanese Localization | P0 | L2 |
| `ui-accessibility-localization.date-time-timezone` | Date Time Timezone | P0 | L2 |
| `ui-accessibility-localization.number-currency-format` | Number Currency Format | P0 | L2 |
| `ui-accessibility-localization.cjk-line-wrapping` | Cjk Line Wrapping | P0 | L2 |
| `ui-accessibility-localization.long-text-and-pseudo-localization` | Long Text And Pseudo Localization | P0 | L2 |
| `ui-accessibility-localization.no-untranslated-key` | No Untranslated Key | P0 | L2 |
| `ui-accessibility-localization.browser-compatibility` | Browser Compatibility | P0 | L2 |
| `ui-accessibility-localization.frontend-error-boundary` | Frontend Error Boundary | P0 | L2 |
| `ui-accessibility-localization.client-side-secret-and-pii-redaction` | Client Side Secret And Pii Redaction | P0 | L2 |
| `ui-accessibility-localization.web-performance-budget` | Web Performance Budget | P0 | L2 |
| `ui-accessibility-localization.large-list-virtualization` | Large List Virtualization | P0 | L2 |
| `ui-accessibility-localization.progressive-stream-render` | Progressive Stream Render | P0 | L2 |
| `ui-accessibility-localization.offline-reconnect-state` | Offline Reconnect State | P0 | L2 |
| `ui-accessibility-localization.session-expiry-ux` | Session Expiry Ux | P0 | L2 |
| `ui-accessibility-localization.dark-mode` | Dark Mode | P1 | L2 |
| `ui-accessibility-localization.high-contrast-mode` | High Contrast Mode | P1 | L2 |
| `ui-accessibility-localization.touch-target-size` | Touch Target Size | P1 | L2 |
| `ui-accessibility-localization.orientation-change` | Orientation Change | P1 | L2 |
| `ui-accessibility-localization.clipboard-policy` | Clipboard Policy | P1 | L2 |
| `ui-accessibility-localization.download-feedback` | Download Feedback | P1 | L2 |
| `ui-accessibility-localization.toast-announcement` | Toast Announcement | P1 | L2 |
| `ui-accessibility-localization.breadcrumb-and-navigation-consistency` | Breadcrumb And Navigation Consistency | P1 | L2 |
| `ui-accessibility-localization.search-filter-state-in-url` | Search Filter State In Url | P1 | L2 |
| `ui-accessibility-localization.back-forward-browser-state` | Back Forward Browser State | P1 | L2 |
| `ui-accessibility-localization.multi-tab-consistency` | Multi Tab Consistency | P1 | L2 |
| `ui-accessibility-localization.frontend-cache-invalidation` | Frontend Cache Invalidation | P1 | L2 |
| `ui-accessibility-localization.accessibility-automated-plus-manual-gate` | Accessibility Automated Plus Manual Gate | P1 | L2 |
| `ui-accessibility-localization.visual-regression` | Visual Regression | P1 | L2 |
| `ui-accessibility-localization.cross-browser-screenshot` | Cross Browser Screenshot | P1 | L2 |
| `ui-accessibility-localization.rtl-layout-readiness` | Rtl Layout Readiness | P1 | L2 |
| `ui-accessibility-localization.font-fallback` | Font Fallback | P1 | L2 |
| `ui-accessibility-localization.timezone-daylight-saving-boundary` | Timezone Daylight Saving Boundary | P1 | L2 |
| `ui-accessibility-localization.locale-specific-sorting` | Locale Specific Sorting | P1 | L2 |
| `ui-accessibility-localization.input-method-editor-cjk` | Input Method Editor Cjk | P1 | L2 |
| `ui-accessibility-localization.mobile-safe-area` | Mobile Safe Area | P1 | L2 |
| `ui-accessibility-localization.network-slow-3g-behavior` | Network Slow 3G Behavior | P1 | L2 |
| `ui-accessibility-localization.theme-customization` | Theme Customization | P2 | L1 |
| `ui-accessibility-localization.density-setting` | Density Setting | P2 | L1 |
| `ui-accessibility-localization.column-customization` | Column Customization | P2 | L1 |
| `ui-accessibility-localization.dashboard-widget-layout` | Dashboard Widget Layout | P2 | L1 |
| `ui-accessibility-localization.guided-tour` | Guided Tour | P2 | L1 |

## Analytics, Administration, Support and Business Operations (`analytics-admin-support`)

Adapter: `external-analytics-admin-harness`. Contexts: `tenant-admin`, `platform-admin`, `support-agent`, `finance-ops`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `analytics-admin-support.task-volume-and-status-metrics` | Task Volume And Status Metrics | P0 | L2 |
| `analytics-admin-support.success-failure-unavailable-separation` | Success Failure Unavailable Separation | P0 | L2 |
| `analytics-admin-support.business-line-quality-metrics` | Business Line Quality Metrics | P0 | L2 |
| `analytics-admin-support.sser-and-human-intervention-metrics` | Sser And Human Intervention Metrics | P0 | L2 |
| `analytics-admin-support.token-credit-cost-metrics` | Token Credit Cost Metrics | P0 | L2 |
| `analytics-admin-support.machine-wall-clock-eta-accuracy` | Machine Wall Clock Eta Accuracy | P0 | L2 |
| `analytics-admin-support.cache-hit-and-savings` | Cache Hit And Savings | P0 | L2 |
| `analytics-admin-support.model-provider-performance` | Model Provider Performance | P0 | L2 |
| `analytics-admin-support.tenant-usage-and-quota` | Tenant Usage And Quota | P0 | L2 |
| `analytics-admin-support.billing-reconciliation-dashboard` | Billing Reconciliation Dashboard | P0 | L2 |
| `analytics-admin-support.metric-definition-versioning` | Metric Definition Versioning | P0 | L2 |
| `analytics-admin-support.data-freshness-and-as-of` | Data Freshness And As Of | P0 | L2 |
| `analytics-admin-support.late-event-and-backfill` | Late Event And Backfill | P0 | L2 |
| `analytics-admin-support.duplicate-event-dedup` | Duplicate Event Dedup | P0 | L2 |
| `analytics-admin-support.admin-user-tenant-project-search` | Admin User Tenant Project Search | P0 | L2 |
| `analytics-admin-support.admin-role-authorization` | Admin Role Authorization | P0 | L2 |
| `analytics-admin-support.admin-change-audit` | Admin Change Audit | P0 | L2 |
| `analytics-admin-support.feature-flag-management` | Feature Flag Management | P0 | L2 |
| `analytics-admin-support.quota-and-limit-management` | Quota And Limit Management | P0 | L2 |
| `analytics-admin-support.support-case-create-and-timeline` | Support Case Create And Timeline | P0 | L2 |
| `analytics-admin-support.support-safe-impersonation` | Support Safe Impersonation | P0 | L2 |
| `analytics-admin-support.support-redacted-diagnostic-view` | Support Redacted Diagnostic View | P0 | L2 |
| `analytics-admin-support.refund-or-credit-adjustment-approval` | Refund Or Credit Adjustment Approval | P0 | L2 |
| `analytics-admin-support.incident-to-affected-run-linkage` | Incident To Affected Run Linkage | P0 | L2 |
| `analytics-admin-support.customer-data-export-support` | Customer Data Export Support | P0 | L2 |
| `analytics-admin-support.customer-deletion-support` | Customer Deletion Support | P0 | L2 |
| `analytics-admin-support.data-correction-with-audit` | Data Correction With Audit | P0 | L2 |
| `analytics-admin-support.fraud-and-abuse-review` | Fraud And Abuse Review | P0 | L2 |
| `analytics-admin-support.analytics-export-csv-json` | Analytics Export Csv Json | P0 | L2 |
| `analytics-admin-support.financial-export` | Financial Export | P0 | L2 |
| `analytics-admin-support.audit-export` | Audit Export | P0 | L2 |
| `analytics-admin-support.dashboard-tenant-isolation` | Dashboard Tenant Isolation | P0 | L2 |
| `analytics-admin-support.sensitive-metric-access-control` | Sensitive Metric Access Control | P0 | L2 |
| `analytics-admin-support.cohort-and-retention` | Cohort And Retention | P1 | L2 |
| `analytics-admin-support.funnel-upload-to-completion` | Funnel Upload To Completion | P1 | L2 |
| `analytics-admin-support.failure-root-cause-trend` | Failure Root Cause Trend | P1 | L2 |
| `analytics-admin-support.model-quality-cost-frontier` | Model Quality Cost Frontier | P1 | L2 |
| `analytics-admin-support.golden-route-certification-status` | Golden Route Certification Status | P1 | L2 |
| `analytics-admin-support.license-review-dashboard` | License Review Dashboard | P1 | L2 |
| `analytics-admin-support.corpus-health-dashboard` | Corpus Health Dashboard | P1 | L2 |
| `analytics-admin-support.provider-health-dashboard` | Provider Health Dashboard | P1 | L2 |
| `analytics-admin-support.queue-capacity-dashboard` | Queue Capacity Dashboard | P1 | L2 |
| `analytics-admin-support.slo-dashboard` | Slo Dashboard | P1 | L2 |
| `analytics-admin-support.anomaly-detection` | Anomaly Detection | P1 | L2 |
| `analytics-admin-support.forecast-usage-capacity` | Forecast Usage Capacity | P1 | L2 |
| `analytics-admin-support.support-sla-and-escalation` | Support Sla And Escalation | P1 | L2 |
| `analytics-admin-support.case-comment-and-attachment` | Case Comment And Attachment | P1 | L2 |
| `analytics-admin-support.case-resolution-and-survey` | Case Resolution And Survey | P1 | L2 |
| `analytics-admin-support.admin-bulk-operation` | Admin Bulk Operation | P1 | L2 |
| `analytics-admin-support.admin-change-preview` | Admin Change Preview | P1 | L2 |
| `analytics-admin-support.config-diff-and-rollback` | Config Diff And Rollback | P1 | L2 |
| `analytics-admin-support.scheduled-report` | Scheduled Report | P1 | L2 |
| `analytics-admin-support.report-subscription` | Report Subscription | P1 | L2 |
| `analytics-admin-support.data-quality-tests` | Data Quality Tests | P1 | L2 |
| `analytics-admin-support.semantic-layer-contract` | Semantic Layer Contract | P1 | L2 |
| `analytics-admin-support.metric-lineage` | Metric Lineage | P1 | L2 |
| `analytics-admin-support.warehouse-backfill-reconciliation` | Warehouse Backfill Reconciliation | P1 | L2 |
| `analytics-admin-support.privacy-safe-aggregation` | Privacy Safe Aggregation | P1 | L2 |
| `analytics-admin-support.dashboard-customization` | Dashboard Customization | P2 | L1 |
| `analytics-admin-support.saved-report` | Saved Report | P2 | L1 |
| `analytics-admin-support.chart-export` | Chart Export | P2 | L1 |
| `analytics-admin-support.admin-recent-actions` | Admin Recent Actions | P2 | L1 |
| `analytics-admin-support.support-macro-template` | Support Macro Template | P2 | L1 |

## Notifications, Scheduled Jobs and Delivery Reliability (`notifications-scheduler`)

Adapter: `external-notification-scheduler-harness`. Contexts: `in-app`, `email`, `webhook`, `scheduled-digest`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `notifications-scheduler.event-to-notification-mapping` | Event To Notification Mapping | P0 | L2 |
| `notifications-scheduler.notification-tenant-and-recipient-authorization` | Notification Tenant And Recipient Authorization | P0 | L2 |
| `notifications-scheduler.template-variable-validation` | Template Variable Validation | P0 | L2 |
| `notifications-scheduler.no-secret-or-pii-leak` | No Secret Or Pii Leak | P0 | L2 |
| `notifications-scheduler.delivery-idempotency` | Delivery Idempotency | P0 | L2 |
| `notifications-scheduler.duplicate-event-suppression` | Duplicate Event Suppression | P0 | L2 |
| `notifications-scheduler.out-of-order-event-policy` | Out Of Order Event Policy | P0 | L2 |
| `notifications-scheduler.retry-and-dead-letter` | Retry And Dead Letter | P0 | L2 |
| `notifications-scheduler.delivery-status` | Delivery Status | P0 | L2 |
| `notifications-scheduler.user-preferences` | User Preferences | P0 | L2 |
| `notifications-scheduler.unsubscribe-and-mandatory-notification-policy` | Unsubscribe And Mandatory Notification Policy | P0 | L2 |
| `notifications-scheduler.timezone-scheduled-delivery` | Timezone Scheduled Delivery | P0 | L2 |
| `notifications-scheduler.quiet-hours` | Quiet Hours | P0 | L2 |
| `notifications-scheduler.task-completion-notification` | Task Completion Notification | P0 | L2 |
| `notifications-scheduler.task-failure-notification` | Task Failure Notification | P0 | L2 |
| `notifications-scheduler.low-credit-notification` | Low Credit Notification | P0 | L2 |
| `notifications-scheduler.approval-request-and-expiry` | Approval Request And Expiry | P0 | L2 |
| `notifications-scheduler.security-alert` | Security Alert | P0 | L2 |
| `notifications-scheduler.payment-and-refund-notification` | Payment And Refund Notification | P0 | L2 |
| `notifications-scheduler.scheduler-job-lock-and-fencing` | Scheduler Job Lock And Fencing | P0 | L2 |
| `notifications-scheduler.scheduler-missed-run-recovery` | Scheduler Missed Run Recovery | P0 | L2 |
| `notifications-scheduler.scheduler-daylight-saving-boundary` | Scheduler Daylight Saving Boundary | P0 | L2 |
| `notifications-scheduler.scheduled-job-cancel` | Scheduled Job Cancel | P0 | L2 |
| `notifications-scheduler.scheduled-job-audit` | Scheduled Job Audit | P0 | L2 |
| `notifications-scheduler.notification-provider-outage` | Notification Provider Outage | P0 | L2 |
| `notifications-scheduler.digest-batching` | Digest Batching | P1 | L2 |
| `notifications-scheduler.rate-limit-per-user` | Rate Limit Per User | P1 | L2 |
| `notifications-scheduler.notification-localization` | Notification Localization | P1 | L2 |
| `notifications-scheduler.email-bounce-and-suppression` | Email Bounce And Suppression | P1 | L2 |
| `notifications-scheduler.email-link-expiry` | Email Link Expiry | P1 | L2 |
| `notifications-scheduler.in-app-read-state` | In App Read State | P1 | L2 |
| `notifications-scheduler.notification-center-pagination` | Notification Center Pagination | P1 | L2 |
| `notifications-scheduler.webhook-notification-channel` | Webhook Notification Channel | P1 | L2 |
| `notifications-scheduler.admin-broadcast-approval` | Admin Broadcast Approval | P1 | L2 |
| `notifications-scheduler.maintenance-notification` | Maintenance Notification | P1 | L2 |
| `notifications-scheduler.weekly-usage-report` | Weekly Usage Report | P1 | L2 |
| `notifications-scheduler.cost-report-notification` | Cost Report Notification | P1 | L2 |
| `notifications-scheduler.project-share-notification` | Project Share Notification | P1 | L2 |
| `notifications-scheduler.comment-mention-notification` | Comment Mention Notification | P1 | L2 |
| `notifications-scheduler.integration-failure-notification` | Integration Failure Notification | P1 | L2 |
| `notifications-scheduler.support-case-update-notification` | Support Case Update Notification | P1 | L2 |
| `notifications-scheduler.notification-sound-setting` | Notification Sound Setting | P2 | L1 |
| `notifications-scheduler.notification-preview` | Notification Preview | P2 | L1 |
| `notifications-scheduler.template-theme` | Template Theme | P2 | L1 |
| `notifications-scheduler.digest-day-selection` | Digest Day Selection | P2 | L1 |
| `notifications-scheduler.notification-search` | Notification Search | P2 | L1 |

## AI-Native Project Factory and Cross-Framework Agent Solution Compiler (`ai-solution-factory`)

Adapter: `external-ai-solution-factory-harness`. Contexts: `import-existing`, `greenfield-generate`, `cross-framework-convert`, `upgrade-and-roundtrip`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `ai-solution-factory.ai-sir-requirement-compilation` | Ai Sir Requirement Compilation | P0 | L2 |
| `ai-solution-factory.ai-sir-model-agent-workflow-tool-rag-memory-interaction-security-runtime-assurance` | Ai Sir Model Agent Workflow Tool Rag Memory Interaction Security Runtime Assurance | P0 | L2 |
| `ai-solution-factory.dify-import-generate-conformance` | Dify Import Generate Conformance | P0 | L2 |
| `ai-solution-factory.universal-rag-generate-conformance` | Universal Rag Generate Conformance | P0 | L2 |
| `ai-solution-factory.langchain-import-generate-conformance` | Langchain Import Generate Conformance | P0 | L2 |
| `ai-solution-factory.langgraph-import-generate-conformance` | Langgraph Import Generate Conformance | P0 | L2 |
| `ai-solution-factory.spring-ai-import-generate-conformance` | Spring Ai Import Generate Conformance | P0 | L2 |
| `ai-solution-factory.pi-agent-import-generate-conformance` | Pi Agent Import Generate Conformance | P0 | L2 |
| `ai-solution-factory.deepseek-harness-conformance` | Deepseek Harness Conformance | P0 | L2 |
| `ai-solution-factory.openharness-conformance` | Openharness Conformance | P0 | L2 |
| `ai-solution-factory.symphony-conformance` | Symphony Conformance | P0 | L2 |
| `ai-solution-factory.openclaw-conformance` | Openclaw Conformance | P0 | L2 |
| `ai-solution-factory.openai-agents-sdk-conformance` | Openai Agents Sdk Conformance | P0 | L2 |
| `ai-solution-factory.google-adk-conformance` | Google Adk Conformance | P0 | L2 |
| `ai-solution-factory.microsoft-agent-framework-conformance` | Microsoft Agent Framework Conformance | P0 | L2 |
| `ai-solution-factory.llamaindex-conformance` | Llamaindex Conformance | P0 | L2 |
| `ai-solution-factory.haystack-conformance` | Haystack Conformance | P0 | L2 |
| `ai-solution-factory.pydanticai-conformance` | Pydanticai Conformance | P0 | L2 |
| `ai-solution-factory.target-capability-negotiation` | Target Capability Negotiation | P0 | L2 |
| `ai-solution-factory.adapter-version-pin` | Adapter Version Pin | P0 | L2 |
| `ai-solution-factory.workflow-graph-semantic-equivalence` | Workflow Graph Semantic Equivalence | P0 | L2 |
| `ai-solution-factory.tool-contract-semantic-equivalence` | Tool Contract Semantic Equivalence | P0 | L2 |
| `ai-solution-factory.rag-retrieval-and-citation-equivalence` | Rag Retrieval And Citation Equivalence | P0 | L2 |
| `ai-solution-factory.memory-semantics-equivalence` | Memory Semantics Equivalence | P0 | L2 |
| `ai-solution-factory.human-approval-and-authority-equivalence` | Human Approval And Authority Equivalence | P0 | L2 |
| `ai-solution-factory.side-effect-and-transaction-equivalence` | Side Effect And Transaction Equivalence | P0 | L2 |
| `ai-solution-factory.normalized-trace-equivalence` | Normalized Trace Equivalence | P0 | L2 |
| `ai-solution-factory.cross-framework-differential` | Cross Framework Differential | P0 | L2 |
| `ai-solution-factory.native-runtime-build-start-test` | Native Runtime Build Start Test | P0 | L2 |
| `ai-solution-factory.security-red-team` | Security Red Team | P0 | L2 |
| `ai-solution-factory.prompt-injection-and-tool-abuse` | Prompt Injection And Tool Abuse | P0 | L2 |
| `ai-solution-factory.deployment-generation` | Deployment Generation | P0 | L2 |
| `ai-solution-factory.observability-generation` | Observability Generation | P0 | L2 |
| `ai-solution-factory.test-and-eval-generation` | Test And Eval Generation | P0 | L2 |
| `ai-solution-factory.import-roundtrip-no-silent-loss` | Import Roundtrip No Silent Loss | P0 | L2 |
| `ai-solution-factory.unsupported-native-feature-disclosure` | Unsupported Native Feature Disclosure | P0 | L2 |
| `ai-solution-factory.e0-e5-p05-evidence` | E0 E5 P05 Evidence | P0 | L2 |
| `ai-solution-factory.visual-dsl-import` | Visual Dsl Import | P1 | L2 |
| `ai-solution-factory.multi-target-portfolio-generation` | Multi Target Portfolio Generation | P1 | L2 |
| `ai-solution-factory.framework-upgrade` | Framework Upgrade | P1 | L2 |
| `ai-solution-factory.provider-model-swap` | Provider Model Swap | P1 | L2 |
| `ai-solution-factory.vector-store-swap` | Vector Store Swap | P1 | L2 |
| `ai-solution-factory.model-serving-adapter` | Model Serving Adapter | P1 | L2 |
| `ai-solution-factory.mcp-a2a-gateway-generation` | Mcp A2A Gateway Generation | P1 | L2 |
| `ai-solution-factory.operator-console-generation` | Operator Console Generation | P1 | L2 |
| `ai-solution-factory.multi-tenant-runtime-generation` | Multi Tenant Runtime Generation | P1 | L2 |
| `ai-solution-factory.finops-and-budget-generation` | Finops And Budget Generation | P1 | L2 |
| `ai-solution-factory.agent-loop-liveness-and-fairness` | Agent Loop Liveness And Fairness | P1 | L2 |
| `ai-solution-factory.graph-dead-end-and-cycle-analysis` | Graph Dead End And Cycle Analysis | P1 | L2 |
| `ai-solution-factory.tool-schema-evolution` | Tool Schema Evolution | P1 | L2 |
| `ai-solution-factory.memory-migration` | Memory Migration | P1 | L2 |
| `ai-solution-factory.rag-index-migration` | Rag Index Migration | P1 | L2 |
| `ai-solution-factory.framework-specific-performance` | Framework Specific Performance | P1 | L2 |
| `ai-solution-factory.framework-specific-cost` | Framework Specific Cost | P1 | L2 |
| `ai-solution-factory.generated-docs-and-runbook` | Generated Docs And Runbook | P1 | L2 |
| `ai-solution-factory.project-evolution` | Project Evolution | P1 | L2 |
| `ai-solution-factory.customer-holdout-route` | Customer Holdout Route | P1 | L2 |
| `ai-solution-factory.framework-template-catalog` | Framework Template Catalog | P2 | L1 |
| `ai-solution-factory.solution-preview-diagram` | Solution Preview Diagram | P2 | L1 |
| `ai-solution-factory.adapter-capability-dashboard` | Adapter Capability Dashboard | P2 | L1 |
| `ai-solution-factory.generated-example-gallery` | Generated Example Gallery | P2 | L1 |
| `ai-solution-factory.migration-estimate-preview` | Migration Estimate Preview | P2 | L1 |

## Data Engineering, Streaming, Lakehouse and Analytics Project Capabilities (`data-bigdata-solution`)

Adapter: `external-data-platform-harness`. Contexts: `batch-pipeline`, `streaming-pipeline`, `lakehouse`, `warehouse-bi`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `data-bigdata-solution.source-connector-ingestion` | Source Connector Ingestion | P0 | L2 |
| `data-bigdata-solution.cdc-exactly-once-or-dedup` | Cdc Exactly Once Or Dedup | P0 | L2 |
| `data-bigdata-solution.schema-registry-and-evolution` | Schema Registry And Evolution | P0 | L2 |
| `data-bigdata-solution.batch-etl-correctness` | Batch Etl Correctness | P0 | L2 |
| `data-bigdata-solution.stream-window-watermark-late-data` | Stream Window Watermark Late Data | P0 | L2 |
| `data-bigdata-solution.kafka-topic-partition-and-offset` | Kafka Topic Partition And Offset | P0 | L2 |
| `data-bigdata-solution.flink-or-spark-streaming-checkpoint` | Flink Or Spark Streaming Checkpoint | P0 | L2 |
| `data-bigdata-solution.spark-batch-job` | Spark Batch Job | P0 | L2 |
| `data-bigdata-solution.lakehouse-table-format` | Lakehouse Table Format | P0 | L2 |
| `data-bigdata-solution.warehouse-load-and-merge` | Warehouse Load And Merge | P0 | L2 |
| `data-bigdata-solution.data-quality-rules` | Data Quality Rules | P0 | L2 |
| `data-bigdata-solution.quarantine-and-reprocessing` | Quarantine And Reprocessing | P0 | L2 |
| `data-bigdata-solution.lineage-and-provenance` | Lineage And Provenance | P0 | L2 |
| `data-bigdata-solution.catalog-and-discovery` | Catalog And Discovery | P0 | L2 |
| `data-bigdata-solution.pii-classification-and-masking` | Pii Classification And Masking | P0 | L2 |
| `data-bigdata-solution.tenant-and-row-column-security` | Tenant And Row Column Security | P0 | L2 |
| `data-bigdata-solution.data-retention-and-deletion` | Data Retention And Deletion | P0 | L2 |
| `data-bigdata-solution.orchestration-dag-retry` | Orchestration Dag Retry | P0 | L2 |
| `data-bigdata-solution.backfill-idempotency` | Backfill Idempotency | P0 | L2 |
| `data-bigdata-solution.pipeline-checkpoint-and-resume` | Pipeline Checkpoint And Resume | P0 | L2 |
| `data-bigdata-solution.source-target-count-and-hash-reconciliation` | Source Target Count And Hash Reconciliation | P0 | L2 |
| `data-bigdata-solution.decimal-timezone-null-semantics` | Decimal Timezone Null Semantics | P0 | L2 |
| `data-bigdata-solution.partitioning-and-file-size` | Partitioning And File Size | P0 | L2 |
| `data-bigdata-solution.small-file-compaction` | Small File Compaction | P0 | L2 |
| `data-bigdata-solution.data-contract-and-schema-compatibility` | Data Contract And Schema Compatibility | P0 | L2 |
| `data-bigdata-solution.observability-freshness-volume-quality` | Observability Freshness Volume Quality | P0 | L2 |
| `data-bigdata-solution.slo-and-alert` | Slo And Alert | P0 | L2 |
| `data-bigdata-solution.cost-and-resource-budget` | Cost And Resource Budget | P0 | L2 |
| `data-bigdata-solution.disaster-recovery` | Disaster Recovery | P0 | L2 |
| `data-bigdata-solution.dashboard-metric-contract` | Dashboard Metric Contract | P0 | L2 |
| `data-bigdata-solution.sql-transformation-test` | Sql Transformation Test | P0 | L2 |
| `data-bigdata-solution.deployment-and-infrastructure` | Deployment And Infrastructure | P0 | L2 |
| `data-bigdata-solution.secret-and-credential-broker` | Secret And Credential Broker | P0 | L2 |
| `data-bigdata-solution.supply-chain-evidence` | Supply Chain Evidence | P0 | L2 |
| `data-bigdata-solution.multi-cloud-object-storage` | Multi Cloud Object Storage | P1 | L2 |
| `data-bigdata-solution.iceberg-delta-hudi-adapter` | Iceberg Delta Hudi Adapter | P1 | L2 |
| `data-bigdata-solution.trino-presto-query` | Trino Presto Query | P1 | L2 |
| `data-bigdata-solution.dbt-project-generation` | Dbt Project Generation | P1 | L2 |
| `data-bigdata-solution.airflow-dag-generation` | Airflow Dag Generation | P1 | L2 |
| `data-bigdata-solution.data-diff-at-scale` | Data Diff At Scale | P1 | L2 |
| `data-bigdata-solution.synthetic-data-generation` | Synthetic Data Generation | P1 | L2 |
| `data-bigdata-solution.privacy-preserving-test-data` | Privacy Preserving Test Data | P1 | L2 |
| `data-bigdata-solution.feature-store-pipeline` | Feature Store Pipeline | P1 | L2 |
| `data-bigdata-solution.vector-data-pipeline` | Vector Data Pipeline | P1 | L2 |
| `data-bigdata-solution.ml-training-data-version` | Ml Training Data Version | P1 | L2 |
| `data-bigdata-solution.real-time-serving-table` | Real Time Serving Table | P1 | L2 |
| `data-bigdata-solution.data-mesh-domain-contract` | Data Mesh Domain Contract | P1 | L2 |
| `data-bigdata-solution.chargeback-cost-allocation` | Chargeback Cost Allocation | P1 | L2 |
| `data-bigdata-solution.autoscaling` | Autoscaling | P1 | L2 |
| `data-bigdata-solution.hot-cold-tiering` | Hot Cold Tiering | P1 | L2 |
| `data-bigdata-solution.cross-region-replication` | Cross Region Replication | P1 | L2 |
| `data-bigdata-solution.data-product-documentation` | Data Product Documentation | P1 | L2 |
| `data-bigdata-solution.business-glossary` | Business Glossary | P1 | L2 |
| `data-bigdata-solution.bi-dashboard-generation` | Bi Dashboard Generation | P1 | L2 |
| `data-bigdata-solution.pipeline-visualization` | Pipeline Visualization | P2 | L1 |
| `data-bigdata-solution.dataset-preview` | Dataset Preview | P2 | L1 |
| `data-bigdata-solution.quality-dashboard` | Quality Dashboard | P2 | L1 |
| `data-bigdata-solution.lineage-search` | Lineage Search | P2 | L1 |
| `data-bigdata-solution.cost-dashboard` | Cost Dashboard | P2 | L1 |

## Commercial Packaging, Evidence, Golden Routes and Customer Acceptance (`commercial-delivery-certification`)

Adapter: `external-commercial-certification-harness`. Contexts: `trial`, `paid-project`, `enterprise-golden-route`, `private-deployment`.

| Feature ID | Title | Priority | Level |
|---|---|---|---|
| `commercial-delivery-certification.deliverable-manifest` | Deliverable Manifest | P0 | L2 |
| `commercial-delivery-certification.source-and-artifact-checksums` | Source And Artifact Checksums | P0 | L2 |
| `commercial-delivery-certification.download-package-integrity` | Download Package Integrity | P0 | L2 |
| `commercial-delivery-certification.license-and-third-party-notice` | License And Third Party Notice | P0 | L2 |
| `commercial-delivery-certification.sbom-aibom-vex` | Sbom Aibom Vex | P0 | L2 |
| `commercial-delivery-certification.build-provenance-and-signature` | Build Provenance And Signature | P0 | L2 |
| `commercial-delivery-certification.immutable-release-candidate` | Immutable Release Candidate | P0 | L2 |
| `commercial-delivery-certification.test-plan-and-result-bundle` | Test Plan And Result Bundle | P0 | L2 |
| `commercial-delivery-certification.raw-and-normalized-evidence` | Raw And Normalized Evidence | P0 | L2 |
| `commercial-delivery-certification.evidence-signature-and-chain` | Evidence Signature And Chain | P0 | L2 |
| `commercial-delivery-certification.known-limitations-and-unsupported-list` | Known Limitations And Unsupported List | P0 | L2 |
| `commercial-delivery-certification.manual-intervention-report` | Manual Intervention Report | P0 | L2 |
| `commercial-delivery-certification.cost-token-credit-wall-clock-report` | Cost Token Credit Wall Clock Report | P0 | L2 |
| `commercial-delivery-certification.architecture-and-operation-docs` | Architecture And Operation Docs | P0 | L2 |
| `commercial-delivery-certification.test-suite-as-deliverable` | Test Suite As Deliverable | P0 | L2 |
| `commercial-delivery-certification.deployment-and-rollback-runbook` | Deployment And Rollback Runbook | P0 | L2 |
| `commercial-delivery-certification.data-migration-and-reconciliation-report` | Data Migration And Reconciliation Report | P0 | L2 |
| `commercial-delivery-certification.security-report` | Security Report | P0 | L2 |
| `commercial-delivery-certification.performance-report` | Performance Report | P0 | L2 |
| `commercial-delivery-certification.e0-e5-certification-stages` | E0 E5 Certification Stages | P0 | L2 |
| `commercial-delivery-certification.p05-deployment-complete-gate` | P05 Deployment Complete Gate | P0 | L2 |
| `commercial-delivery-certification.waiver-policy-and-expiry` | Waiver Policy And Expiry | P0 | L2 |
| `commercial-delivery-certification.customer-hidden-holdout` | Customer Hidden Holdout | P0 | L2 |
| `commercial-delivery-certification.customer-acceptance-signoff` | Customer Acceptance Signoff | P0 | L2 |
| `commercial-delivery-certification.golden-route-repeatability` | Golden Route Repeatability | P0 | L2 |
| `commercial-delivery-certification.golden-route-current-version-recertification` | Golden Route Current Version Recertification | P0 | L2 |
| `commercial-delivery-certification.500k-loc-route` | 500K Loc Route | P0 | L2 |
| `commercial-delivery-certification.one-million-loc-route` | One Million Loc Route | P0 | L2 |
| `commercial-delivery-certification.independent-verifier` | Independent Verifier | P0 | L2 |
| `commercial-delivery-certification.support-handover` | Support Handover | P0 | L2 |
| `commercial-delivery-certification.sla-and-support-scope` | Sla And Support Scope | P0 | L2 |
| `commercial-delivery-certification.retention-and-evidence-availability` | Retention And Evidence Availability | P0 | L2 |
| `commercial-delivery-certification.entitlement-before-download` | Entitlement Before Download | P0 | L2 |
| `commercial-delivery-certification.revoked-entitlement-download-denial` | Revoked Entitlement Download Denial | P0 | L2 |
| `commercial-delivery-certification.commercial-edition-feature-matrix` | Commercial Edition Feature Matrix | P1 | L2 |
| `commercial-delivery-certification.quotation-and-scope-binding` | Quotation And Scope Binding | P1 | L2 |
| `commercial-delivery-certification.change-order` | Change Order | P1 | L2 |
| `commercial-delivery-certification.milestone-acceptance` | Milestone Acceptance | P1 | L2 |
| `commercial-delivery-certification.partial-delivery` | Partial Delivery | P1 | L2 |
| `commercial-delivery-certification.delivery-resume` | Delivery Resume | P1 | L2 |
| `commercial-delivery-certification.customer-branding` | Customer Branding | P1 | L2 |
| `commercial-delivery-certification.private-registry-publish` | Private Registry Publish | P1 | L2 |
| `commercial-delivery-certification.offline-media-bundle` | Offline Media Bundle | P1 | L2 |
| `commercial-delivery-certification.installation-validation` | Installation Validation | P1 | L2 |
| `commercial-delivery-certification.training-material` | Training Material | P1 | L2 |
| `commercial-delivery-certification.operator-certification` | Operator Certification | P1 | L2 |
| `commercial-delivery-certification.release-notes` | Release Notes | P1 | L2 |
| `commercial-delivery-certification.upgrade-compatibility` | Upgrade Compatibility | P1 | L2 |
| `commercial-delivery-certification.renewal-recertification` | Renewal Recertification | P1 | L2 |
| `commercial-delivery-certification.customer-defect-regression` | Customer Defect Regression | P1 | L2 |
| `commercial-delivery-certification.support-case-evidence-link` | Support Case Evidence Link | P1 | L2 |
| `commercial-delivery-certification.independent-legal-license-review` | Independent Legal License Review | P1 | L2 |
| `commercial-delivery-certification.psirt-contact-and-policy` | Psirt Contact And Policy | P1 | L2 |
| `commercial-delivery-certification.business-continuity-evidence` | Business Continuity Evidence | P1 | L2 |
| `commercial-delivery-certification.delivery-portal-ui` | Delivery Portal Ui | P2 | L1 |
| `commercial-delivery-certification.certificate-pdf` | Certificate Pdf | P2 | L1 |
| `commercial-delivery-certification.evidence-browser` | Evidence Browser | P2 | L1 |
| `commercial-delivery-certification.project-status-share-link` | Project Status Share Link | P2 | L1 |
| `commercial-delivery-certification.customer-feedback-survey` | Customer Feedback Survey | P2 | L1 |

