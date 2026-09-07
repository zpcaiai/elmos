# Anti-Fraud and Honest Test Execution Policy

A test result is invalid when it is obtained by modifying the target obligation rather than satisfying it. The following actions are prohibited:

- deleting, disabling, skipping or quarantining a failing Critical or High case;
- weakening an assertion, tolerance, permission, security control or acceptance criterion;
- editing approved requirements, architecture or public contracts solely to make generated code pass;
- replacing a required real integration with a mock-only test;
- hiding warnings, flaky history, repair attempts, partial writes or failed environments;
- fabricating, re-signing or selectively omitting evidence;
- granting broader permissions or cross-tenant access during tests;
- allowing the implementation-producing model or agent to be the sole correctness oracle.

Any detected anti-fraud signal is a release blocker and must be reported separately from ordinary product defects.
