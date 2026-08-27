# Top-up Flow

1. receive payment-provider success notification or verified top-up request;
2. create/lock idempotency record using provider payment identity;
3. validate request hash/payment attributes;
4. insert topup row;
5. lock wallet;
6. credit available balance;
7. write TOPUP ledger entry;
8. post balanced journal;
9. mark topup COMPLETED;
10. mark idempotency SUCCEEDED with resource/response;
11. write outbox TOPUP_COMPLETED;
12. scheduler credit-resume projector moves eligible WAITING_FOR_CREDIT work back to READY.

All steps 4–11 occur in one local Billing transaction.
