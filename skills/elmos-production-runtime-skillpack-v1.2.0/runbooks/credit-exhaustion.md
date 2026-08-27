# Credit Exhaustion

- stop new billable calls;
- allow already-reserved confirmed calls to finish;
- checkpoint work;
- move affected work to WAITING_FOR_CREDIT;
- top-up credits wallet exactly once;
- TOPUP_COMPLETED event wakes credit-resume logic;
- resume without replaying succeeded work.
