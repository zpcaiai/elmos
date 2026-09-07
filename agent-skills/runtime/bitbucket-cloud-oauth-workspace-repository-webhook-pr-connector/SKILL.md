---
name: bitbucket-cloud-oauth-workspace-repository-webhook-pr-connector
description: "Implement Bitbucket Cloud OAuth/access-token authentication, workspace/project/repository synchronization, API 2.0 pagination and filtering, refs, branch restrictions, signed webhooks, pull requests, build statuses, Git transport, access revocation, and reconciliation."
---

# Objective

Implement Bitbucket Cloud through the unified SCM contract.

# Provider profile

Fixed production endpoints:

```text
webBaseUrl
https://bitbucket.org

restBaseUrl
https://api.bitbucket.org/2.0

oauthAuthorizeUrl
https://bitbucket.org/site/oauth2/authorize

oauthTokenUrl
https://bitbucket.org/site/oauth2/access_token
