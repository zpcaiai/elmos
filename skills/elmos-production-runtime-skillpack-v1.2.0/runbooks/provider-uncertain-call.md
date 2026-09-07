# Provider Uncertain Call

If the client times out after provider may have accepted the request:
1. do not immediately issue a new provider call;
2. inspect persisted model-call receipt/provider request id;
3. reconcile provider state if API supports it;
4. settle confirmed usage;
5. only retry a fresh provider call when previous non-acceptance is established.
