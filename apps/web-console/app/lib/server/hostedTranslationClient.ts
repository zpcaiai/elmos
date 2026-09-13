import { createHash } from "node:crypto";
import type { TranslationJob, TranslationLanguageId, TranslationSemanticCoverage, TranslationBehaviorCoverage } from "../contracts";
import { GenerationRunnerError } from "./generationRunner";
import { call, validateHostedArtifactTicket, type ControlPlaneJob, type HostedArtifactTicket } from "./hostedExecutionClient";
import { readBoundedRequestBody } from "./boundedRequestBody";
import { validateTranslationConversion } from "./translationConversionReport";

type Context = { tenantId: string; actor: string; accessToken?: string };
type HostedJob = ControlPlaneJob & { businessLine: string; jobKind: string; translation?: Record<string, unknown> };
function reject(code:string):never {throw new GenerationRunnerError(502,code);}
const terminal = new Set(["SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST"]);
const filenames = { artifact: "repository-migration-artifact.zip", json: "reports/functional-conversion-report.json",
  markdown: "reports/FUNCTION_CONVERSION_REPORT.md", bundle: "evidence/FUNCTION_CONVERSION_REPORT_BUNDLE.zip" };
const record=(value: unknown): value is Record<string,unknown>=>!!value && typeof value==="object" && !Array.isArray(value);
const count=(value: unknown): value is number=>Number.isSafeInteger(value) && Number(value)>=0;
function counts(value:unknown,keys:readonly string[]):Record<string,number> {
  if(!record(value) || Object.keys(value).some(key=>!keys.includes(key)) || Object.values(value).some(item=>!count(item)))
    reject("TRANSLATION_HOSTED_RESULT_COUNTS_INVALID");
  return Object.fromEntries(keys.map(key=>[key,Number(value[key]??0)]));
}
function details(job:TranslationJob,receipt:Record<string,unknown>):void {
  if(!count(receipt.workUnitCount) || !count(receipt.readyCount) || !count(receipt.includedUnitCount)
    || receipt.includedUnitCount>receipt.readyCount || receipt.readyCount>receipt.workUnitCount
    || typeof receipt.repositoryComplete!=="boolean" || typeof receipt.snapshotSha256!=="string"
    || !/^[a-f0-9]{64}$/.test(receipt.snapshotSha256))reject("TRANSLATION_HOSTED_RESULT_COUNTS_INVALID");
  const batch=counts(receipt.statusCounts,["PASSED","FAILED","SKIPPED_NO_CASES","SKIPPED_NOT_READY"]);
  if(Object.values(batch).reduce((sum,item)=>sum+item,0)!==receipt.workUnitCount || batch.PASSED!==receipt.includedUnitCount)
    reject("TRANSLATION_HOSTED_RESULT_COUNTS_INVALID");
  job.workUnitCount=receipt.workUnitCount;job.readyCount=receipt.readyCount;job.includedUnitCount=receipt.includedUnitCount;
  job.statusCounts=batch;job.repositoryComplete=receipt.repositoryComplete;job.snapshotSha256=receipt.snapshotSha256;
  if(job.status==="COMPLETE" && receipt.repositoryComplete!==true)reject("TRANSLATION_HOSTED_RESULT_COMPLETENESS_INVALID");
  const build=receipt.buildVerification;
  if(!record(build) || !["PASSED","FAILED","NOT_RUN"].includes(String(build.status)) || !record(build.toolchain)
    || build.toolchain.language!==job.targetLanguage || typeof build.toolchain.version!=="string"
    || !Array.isArray(build.commands) || build.commands.length>100 || build.commands.some(command=>!record(command)
      || !Array.isArray(command.command) || command.command.some(arg=>typeof arg!=="string")
      || typeof command.stdout!=="string" || typeof command.stderr!=="string"))reject("TRANSLATION_HOSTED_RESULT_BUILD_INVALID");
  job.buildVerification=build as TranslationJob["buildVerification"];
  if(receipt.semanticCoverage!==undefined) {
    const semantic=receipt.semanticCoverage;
    if(!record(semantic) || semantic.profile!=="compiler-semantic-symbol-coverage-v1" || semantic.sourceLanguage!==job.sourceLanguage
      || !["PASSED","FAILED","NOT_RUN"].includes(String(semantic.inventoryStatus)) || !["PASSED","LIMITED"].includes(String(semantic.status))
      || typeof semantic.complete!=="boolean" || !count(semantic.subjectCount))reject("TRANSLATION_HOSTED_RESULT_COVERAGE_INVALID");
    const counted=counts(semantic.statusCounts,["BLOCKED","FAILED","NOT_RUN","PASSED","UNKNOWN"]);
    if(Object.values(counted).reduce((sum,item)=>sum+item,0)!==semantic.subjectCount)reject("TRANSLATION_HOSTED_RESULT_COVERAGE_INVALID");
    job.semanticCoverage={...semantic,statusCounts:counted} as TranslationSemanticCoverage;
  }
  if(receipt.behaviorCoverage!==undefined) {
    const behavior=receipt.behaviorCoverage;
    if(!record(behavior) || behavior.profile!=="typed-pure-function-v1" || !["FAILED","NOT_RUN","PASSED","UNKNOWN"].includes(String(behavior.status))
      || typeof behavior.complete!=="boolean" || behavior.workUnitCount!==receipt.workUnitCount
      || ["accountedWorkUnitCount","attemptedWorkUnitCount","unresolvedWorkUnitCount","behaviorCaseCount"].some(key=>!count(behavior[key]))
      || behavior.behaviorCaseCountScope!=="PASSED_WORK_UNITS_ONLY" || behavior.evidenceStrength!=="LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON"
      || behavior.independentVerificationStatus!=="NOT_RUN" || behavior.externalVerificationStatus!=="NOT_RUN")reject("TRANSLATION_HOSTED_RESULT_COVERAGE_INVALID");
    const counted=counts(behavior.statusCounts,["FAILED","NOT_RUN","PASSED","UNKNOWN"]);
    if(Object.values(counted).reduce((sum,item)=>sum+item,0)!==receipt.workUnitCount)reject("TRANSLATION_HOSTED_RESULT_COVERAGE_INVALID");
    job.behaviorCoverage={...behavior,statusCounts:counted} as TranslationBehaviorCoverage;
  }
}

async function ticket(context: Context, job: HostedJob, role: string, filename: string): Promise<HostedArtifactTicket> {
  const expected = job.artifacts?.filter(value => value.role === role && value.filename === filename);
  if (expected?.length !== 1) throw new GenerationRunnerError(409, "TRANSLATION_ARTIFACT_NOT_READY");
  const value = validateHostedArtifactTicket(await call(context,
    `/api/v1/execution/jobs/${encodeURIComponent(job.jobId)}/artifacts/${role}/download-ticket?filename=${encodeURIComponent(filename)}`, "POST"));
  if (value.contentSha256 !== expected[0].contentSha256 || value.byteSize !== expected[0].byteSize
      || value.filename !== filename.split("/").at(-1)) reject("HOSTED_TRANSLATION_TICKET_IDENTITY_MISMATCH");
  return value;
}

async function rawJob(context: Context, id: string): Promise<HostedJob> {
  if (!/^job-[0-9a-f-]{36}$/.test(id)) throw new GenerationRunnerError(400, "TRANSLATION_HOSTED_JOB_ID_INVALID");
  const value = await call<HostedJob>(context, `/api/v1/execution/jobs/${encodeURIComponent(id)}`, "GET");
  if (value.jobId !== id || value.organizationId !== context.tenantId || value.businessLine !== "TRANSLATION"
      || value.jobKind !== "translate-pipeline-v1" || !value.translation) reject("TRANSLATION_HOSTED_JOB_SUBJECT_INVALID");
  return value;
}

async function mapped(context: Context, value: HostedJob): Promise<TranslationJob> {
  const subject = value.translation!;
  for (const field of ["tenantId","actor","repositoryRef","repositoryWorkspaceId","casesBundleId","sourceLanguage","targetLanguage",
    "repositoryProfile","repositoryEvidenceRef","repositoryEvidenceSha256","inputSha256"]) {
    if (typeof subject[field] !== "string" || !subject[field]) reject("TRANSLATION_HOSTED_JOB_SUBJECT_INVALID");
  }
  if (subject.tenantId !== context.tenantId || subject.actor !== value.actorId || subject.repositoryExecutionStatus !== "PASSED"
      || !Number.isSafeInteger(subject.repositoryEvidenceBytes)) reject("TRANSLATION_HOSTED_JOB_SUBJECT_INVALID");
  const status: TranslationJob["status"] = value.status === "SUCCEEDED" ? "COMPLETE" : value.status === "PARTIAL" ? "PARTIAL"
    : value.status === "CANCELLED" ? "CANCELLED" : value.status === "QUEUED" ? "QUEUED"
    : value.status === "CLAIMED" ? "PRECHECK" : value.status === "RUNNING" ? "RUNNING" : "BLOCKED";
  const job: TranslationJob = {
    id:value.jobId,tenantId:context.tenantId,actor:value.actorId,createdAt:value.createdAt,
    updatedAt:value.finishedAt ?? value.startedAt ?? value.createdAt,
    repositoryRef:String(subject.repositoryRef),workspaceId:String(subject.repositoryWorkspaceId),repositoryWorkspaceId:String(subject.repositoryWorkspaceId),
    casesBundleId:String(subject.casesBundleId),sourceLanguage:subject.sourceLanguage as TranslationLanguageId,targetLanguage:subject.targetLanguage as TranslationLanguageId,
    repositoryExecutionStatus:"PASSED",repositoryProfile:String(subject.repositoryProfile),repositoryEvidenceRef:String(subject.repositoryEvidenceRef),
    repositoryEvidenceSha256:String(subject.repositoryEvidenceSha256),repositoryEvidenceBytes:Number(subject.repositoryEvidenceBytes),
    status,stage:status === "QUEUED" ? "queued" : status === "PRECHECK" ? "preflight" : status === "RUNNING" ? "pipeline"
      : status === "CANCELLED" ? "cancelled" : status === "BLOCKED" ? "blocked" : "complete",
    progress:value.progress,executor:"ROOTLESS_CONTAINER",recoveryAttempts:0,artifactReady:false,reportReady:false,
    independentVerificationStatus:"NOT_RUN",externalVerificationStatus:"NOT_RUN",certificationStatus:"NOT_CERTIFIED",logs:[],
    ...(value.failureCode ? { reason:value.failureCode } : {}),
  };
  const receipts = value.artifacts?.filter(artifact => artifact.role === "GATE_REPORT" && artifact.filename === "gate/translation-job.json") ?? [];
  if (!terminal.has(value.status) || receipts.length === 0) {
    if (status === "COMPLETE" || status === "PARTIAL") reject("TRANSLATION_HOSTED_RESULT_MISSING");
    return job;
  }
  const grant = await ticket(context,value,"GATE_REPORT","gate/translation-job.json");
  if (grant.byteSize > 2 * 1024 * 1024) reject("TRANSLATION_HOSTED_RESULT_SIZE_LIMIT");
  const signal = AbortSignal.timeout(15_000);
  const response = await fetch(grant.downloadUrl,{signal,cache:"no-store",redirect:"error"});
  if (!response.ok) reject("TRANSLATION_HOSTED_RESULT_UNAVAILABLE");
  const text = await readBoundedRequestBody({headers:response.headers,body:response.body,signal},2 * 1024 * 1024,15_000);
  if (Buffer.byteLength(text) !== grant.byteSize || createHash("sha256").update(text).digest("hex") !== grant.contentSha256)
    reject("TRANSLATION_HOSTED_RESULT_DIGEST_MISMATCH");
  const receipt = JSON.parse(text) as Record<string,unknown>;
  if (receipt.schemaVersion !== "translation-hosted-result-v1" || receipt.tenantId !== context.tenantId
    || receipt.inputSha256 !== subject.inputSha256 || receipt.repositoryRef !== subject.repositoryRef
    || receipt.sourceLanguage !== subject.sourceLanguage || receipt.targetLanguage !== subject.targetLanguage
    || receipt.certificationStatus !== "NOT_CERTIFIED" || receipt.independentVerification !== "NOT_RUN" || receipt.externalCertification !== "NOT_RUN"
    || (status === "COMPLETE" && receipt.status !== "COMPLETE") || (status === "PARTIAL" && receipt.status !== "PARTIAL"))
      reject("TRANSLATION_HOSTED_RESULT_SUBJECT_INVALID");
  const conversion = validateTranslationConversion(receipt.functionalConversion,receipt.workUnitCount);
  details(job,receipt);
  job.reportReady=true;job.reportJson=conversion.jsonReport;job.reportMarkdown=conversion.markdownReport;
  if (conversion.reportBundle) job.reportBundle=conversion.reportBundle;
  job.conversionSummary=conversion.summary;
  // Receipt cannot override the queue's cancellation/failure decision.
  job.artifactReady=(status === "COMPLETE" || status === "PARTIAL") && conversion.summary.codeArtifactReady;
  if (job.artifactReady) {
    if (typeof receipt.artifactSha256 !== "string" || !/^[a-f0-9]{64}$/.test(receipt.artifactSha256)
      || !Number.isSafeInteger(receipt.artifactSize) || Number(receipt.artifactSize)<1) reject("TRANSLATION_HOSTED_ARTIFACT_INVALID");
    job.artifactSha256=String(receipt.artifactSha256);job.artifactSize=Number(receipt.artifactSize);
    if(typeof receipt.artifactManifestSha256!=="string" || !/^[a-f0-9]{64}$/.test(receipt.artifactManifestSha256))
      reject("TRANSLATION_HOSTED_ARTIFACT_INVALID");
    job.artifactManifestSha256=receipt.artifactManifestSha256;
  }
  return job;
}

export async function createHostedTranslationJob(context: Context, request: Record<string,unknown>, intentKey?: string | null): Promise<TranslationJob> {
  const fields=["repositoryWorkspaceId","casesBundleId","sourceLanguage","targetLanguage"];
  if (Object.keys(request).some(key => !fields.includes(key)) || fields.some(key => typeof request[key] !== "string" || !request[key]))
    throw new GenerationRunnerError(400,"TRANSLATION_HOSTED_REPOSITORY_REQUEST_REQUIRED");
  const payload=Object.fromEntries(fields.map(key => [key,request[key]]));
  if (intentKey && !/^[a-zA-Z0-9._-]{1,96}$/.test(intentKey)) throw new GenerationRunnerError(400,"TRANSLATION_IDEMPOTENCY_KEY_INVALID");
  const idempotencyKey=createHash("sha256").update(JSON.stringify([context.tenantId,context.actor,intentKey ?? null,payload])).digest("hex");
  const result=await call<{jobId:string}>(context,"/api/v1/execution/jobs","POST",{
    businessLine:"TRANSLATION",jobKind:"translate-pipeline-v1",idempotencyKey,payload,maxAttempts:1,budgetWallSeconds:3600,
  });
  return getHostedTranslationJob(context,result.jobId);
}
export async function getHostedTranslationJob(context: Context,id: string): Promise<TranslationJob> { return mapped(context,await rawJob(context,id)); }
export async function cancelHostedTranslationJob(context: Context,id: string): Promise<TranslationJob> {
  await rawJob(context,id);
  await call(context,`/api/v1/execution/jobs/${encodeURIComponent(id)}`,"DELETE");
  return getHostedTranslationJob(context,id);
}
export async function hostedTranslationArtifactTicket(context: Context,id: string,format: keyof typeof filenames): Promise<HostedArtifactTicket> {
  const raw=await rawJob(context,id);const job=await mapped(context,raw);
  const descriptor=format === "artifact" ? {bytes:job.artifactSize,sha256:job.artifactSha256}
    : format === "markdown" ? job.reportMarkdown : format === "json" ? job.reportJson : job.reportBundle;
  if (!(format === "artifact" ? job.artifactReady : job.reportReady) || !descriptor)
    throw new GenerationRunnerError(409,"TRANSLATION_ARTIFACT_NOT_READY");
  const grant=await ticket(context,raw,format === "artifact" ? "PROJECT_ARCHIVE" : format === "bundle" ? "EVIDENCE_PACK" : "TEST_REPORT",filenames[format]);
  if (grant.byteSize !== descriptor.bytes || grant.contentSha256 !== descriptor.sha256) reject("TRANSLATION_HOSTED_REPORT_IDENTITY_MISMATCH");
  return grant;
}
