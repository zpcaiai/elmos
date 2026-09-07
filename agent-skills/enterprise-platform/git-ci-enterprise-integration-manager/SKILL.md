---
name: git-ci-enterprise-integration-manager
description: Govern tenant-bound least-privilege GitHub, GitLab, Bitbucket, enterprise Git, webhook, CI/CD, issue, and notification integrations. Use for repository installation, PR/MR checks, tokens, or offline Git.
---

# Git CI Enterprise Integration Manager

Read `../references/batch-12-enterprise-platform.md`. Request only needed repository/check/PR scopes, prefer short credentials, verify webhooks, restrict untrusted forks, revoke on uninstall and link each CI status to a Migration Run. Keep tokens out of Runner logs.

Admin-by-default, unsigned webhooks or cross-tenant repository access blocks T-B/T-G.
