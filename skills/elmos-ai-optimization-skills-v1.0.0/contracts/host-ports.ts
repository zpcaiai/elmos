/** Logical ports; brand is a compile-time distinction, not runtime authentication. */
declare const trusted: unique symbol;
export interface RevisionBinding {repository: string; snapshot: string; generation: string;}
export interface TrustedScope {readonly [trusted]: true; tenant: string; principal: string; aclEpoch: number; securityContextRef: string; revisions: readonly RevisionBinding[];}
export interface SourceAnchor extends RevisionBinding {path: string; blobDigest: string; startByte: number; endByte: number; symbol: string;}
export interface ContextRequest {requestId: string; query: string; mode: 'auto'|'exact'|'lexical'|'hybrid'; selector?:{path?:string;symbol?:string}; snapshotRefs:readonly string[];topK:number;contextTokenBudget:number;}
export interface EvidenceContext {status:'ok'|'insufficient_evidence'|'degraded';scopeDigest:string;items:readonly {anchor:SourceAnchor;text:string;truncated:boolean;evidenceRef:string}[];}
export interface ScopeResolver {resolve(sessionRef:string,snapshots:readonly string[]):Promise<TrustedScope>;revalidate(scope:TrustedScope):Promise<void>;}
export interface EvidenceContextService {query(scope:TrustedScope,request:ContextRequest,signal:AbortSignal):Promise<EvidenceContext>;}
export interface ActionIntent {runRef:string;logicalStep:string;baseRevision:string;intentDigest:string;artifactRef:string;budgetRef:string;verificationPlanRef:string;}
export interface Receipt {actionId:string;state:'SUCCEEDED'|'FAILED'|'UNKNOWN_RESULT';receiptRef?:string;}
export interface ExecutionGateway {propose(scope:TrustedScope,intent:ActionIntent):Promise<string>;dispatch(actionId:string,hostCapabilityRef:string):Promise<Receipt>;reconcile(actionId:string):Promise<Receipt>;}
export interface AgentSubflowPort {advance(scope:TrustedScope,input:{runRef:string;graphVersion:string;budgetRef:string;checkpointRef?:string},signal:AbortSignal):Promise<{status:'DONE'|'NEEDS_INPUT'|'ACTION_PROPOSED'|'BLOCKED'|'FAILED';checkpointRef:string;evidenceRefs:readonly string[];intentRef?:string}>;}
export interface AcceptanceService {evaluate(scope:TrustedScope,revisions:readonly string[],sealedEvidenceRef:string):Promise<{decisionRef:string}>;}
