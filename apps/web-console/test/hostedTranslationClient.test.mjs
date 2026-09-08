import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { createHostedTranslationJob, getHostedTranslationJob, cancelHostedTranslationJob,
  hostedTranslationArtifactTicket } from '../app/lib/server/hostedTranslationClient.ts';

const context={tenantId:'tenant-fixture',actor:'actor-fixture',accessToken:'fixture-token'};
const id='job-00000000-0000-4000-8000-000000000001';
const payload={repositoryWorkspaceId:'workspace-fixture',casesBundleId:'cases-fixture',sourceLanguage:'python',targetLanguage:'typescript'};
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function queued() {return {jobId:id,organizationId:context.tenantId,actorId:context.actor,businessLine:'TRANSLATION',
  jobKind:'translate-pipeline-v1',status:'QUEUED',stage:'queued',progress:0,createdAt:'2026-09-07T00:00:00Z',artifacts:[],
  translation:{...payload,tenantId:context.tenantId,actor:context.actor,repositoryRef:'local:translation-launcher-fixture',inputSha256:'b'.repeat(64),
    repositoryExecutionStatus:'PASSED',repositoryProfile:'typed-pure-function-v1',repositoryEvidenceRef:'fixture',repositoryEvidenceSha256:'a'.repeat(64),repositoryEvidenceBytes:100}};}
function environment(t,fetcher) {
  const keys=['NODE_ENV','ELMOS_CONTROL_PLANE_BASE_URL','ELMOS_GENERATION_ARTIFACT_DOWNLOAD_ALLOWED_HOSTS'];
  const previous=Object.fromEntries(keys.map(key=>[key,process.env[key]]));const original=globalThis.fetch;
  process.env.NODE_ENV='production';process.env.ELMOS_CONTROL_PLANE_BASE_URL='https://control.example.test';
  process.env.ELMOS_GENERATION_ARTIFACT_DOWNLOAD_ALLOWED_HOSTS='objects.example.test';globalThis.fetch=fetcher;
  t.after(()=>{globalThis.fetch=original;for(const key of keys){if(previous[key]===undefined)delete process.env[key];else process.env[key]=previous[key];}});
}
const json=value=>new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});

test('hosted translation submits the real queue kind with authenticated subject and one attempt',async t=>{
  const calls=[];
  environment(t,async(url,request)=>{
    calls.push({url,request});assert.equal(request.headers.Authorization,'Bearer fixture-token');
    assert.equal(request.headers['X-ELMOS-Organization-ID'],context.tenantId);
    return json(request.method==='POST'?{jobId:id}:queued());
  });
  assert.equal((await createHostedTranslationJob(context,payload,'intent-1')).status,'QUEUED');
  const submitted=JSON.parse(calls[0].request.body);
  assert.equal(submitted.jobKind,'translate-pipeline-v1');assert.equal(submitted.businessLine,'TRANSLATION');
  assert.equal(submitted.maxAttempts,1);assert.deepEqual(submitted.payload,payload);assert.match(submitted.idempotencyKey,/^[a-f0-9]{64}$/);
  await createHostedTranslationJob(context,payload,'intent-1');assert.equal(JSON.parse(calls[2].request.body).idempotencyKey,submitted.idempotencyKey);
  await assert.rejects(createHostedTranslationJob(context,{...payload,source:'raw-code'}));
});

test('cancellation authorizes the queue subject and cannot cross tenants',async t=>{
  let crossTenant=true,cancelled=false,deletes=0;
  environment(t,async(url,request)=>{
    if(request.method==='DELETE'){deletes++;cancelled=true;return json({status:'CANCELLED'});}
    return json({...queued(),organizationId:crossTenant?'other-tenant':context.tenantId,status:cancelled?'CANCELLED':'QUEUED'});
  });
  await assert.rejects(cancelHostedTranslationJob(context,id),/SUBJECT_INVALID/);assert.equal(deletes,0);
  crossTenant=false;assert.equal((await cancelHostedTranslationJob(context,id)).status,'CANCELLED');assert.equal(deletes,1);
});

test('production translation cannot fall back when control-plane binding or token is absent',async t=>{
  environment(t,async()=>{throw new Error('unexpected fetch');});delete process.env.ELMOS_CONTROL_PLANE_BASE_URL;
  await assert.rejects(getHostedTranslationJob(context,id),/CONTROL_PLANE_NOT_CONFIGURED/);
  await assert.rejects(getHostedTranslationJob({...context,accessToken:undefined},id),/ACCOUNT_ACCESS_TOKEN_REQUIRED/);
});

test('successful queue state requires a tenant-bound digest-verified result receipt',async t=>{
  let phase='missing';const body=Buffer.from(JSON.stringify({schemaVersion:'translation-hosted-result-v1',tenantId:'other'}));
  const artifact={role:'GATE_REPORT',filename:'gate/translation-job.json',contentSha256:sha(body),byteSize:body.length};
  environment(t,async(url)=>{
    if(String(url).startsWith('https://objects.example.test/'))return new Response(phase==='digest'?Buffer.from('{}'):body);
    if(String(url).includes('download-ticket'))return json({downloadUrl:'https://objects.example.test/receipt',filename:phase==='filename'?'other.json':'translation-job.json',
      contentSha256:artifact.contentSha256,byteSize:artifact.byteSize,expiresInSeconds:60});
    return json({...queued(),status:'SUCCEEDED',artifacts:phase==='missing'?[]:[artifact]});
  });
  await assert.rejects(getHostedTranslationJob(context,id),/RESULT_MISSING/);
  phase='filename';await assert.rejects(getHostedTranslationJob(context,id),/TICKET_IDENTITY_MISMATCH/);
  phase='digest';await assert.rejects(getHostedTranslationJob(context,id),/RESULT_DIGEST_MISMATCH/);
  phase='subject';await assert.rejects(getHostedTranslationJob(context,id),/RESULT_SUBJECT_INVALID/);
});

test('actual launcher receipt supports status and exact artifact/report tickets without promoting cancellation',
  {skip:!process.env.ELMOS_TRANSLATION_VERIFIED_FIXTURE},async t=>{
    const receipt=JSON.parse(await readFile(`${process.env.ELMOS_TRANSLATION_VERIFIED_FIXTURE}/output/gate/translation-job.json`,'utf8'));
    const bytes=Buffer.from(JSON.stringify(receipt));let cancelled=false,substitute=false;
    const artifacts=[{role:'GATE_REPORT',filename:'gate/translation-job.json',contentSha256:sha(bytes),byteSize:bytes.length},
      {role:'PROJECT_ARCHIVE',filename:'repository-migration-artifact.zip',contentSha256:receipt.artifactSha256,byteSize:receipt.artifactSize},
      {role:'TEST_REPORT',filename:'reports/functional-conversion-report.json',contentSha256:receipt.reportJson.sha256,byteSize:receipt.reportJson.bytes}];
    environment(t,async(url)=>{
      if(String(url).startsWith('https://objects.example.test/'))return new Response(bytes);
      if(String(url).includes('download-ticket')) {
        const name=new URL(url).searchParams.get('filename'),found=artifacts.find(value=>value.filename===name);assert.ok(found);
        return json({downloadUrl:'https://objects.example.test/'+encodeURIComponent(name),filename:name.split('/').at(-1),
          contentSha256:substitute && found.role==='PROJECT_ARCHIVE'?'0'.repeat(64):found.contentSha256,byteSize:found.byteSize,expiresInSeconds:60});
      }
      return json({...queued(),status:cancelled?'CANCELLED':'SUCCEEDED',artifacts});
    });
    const job=await getHostedTranslationJob(context,id);assert.equal(job.status,'COMPLETE');assert.equal(job.repositoryComplete,true);
    assert.equal(job.semanticCoverage.complete,true);assert.equal(job.behaviorCoverage.complete,true);
    assert.equal((await hostedTranslationArtifactTicket(context,id,'artifact')).contentSha256,receipt.artifactSha256);
    assert.equal((await hostedTranslationArtifactTicket(context,id,'json')).contentSha256,receipt.reportJson.sha256);
    substitute=true;await assert.rejects(hostedTranslationArtifactTicket(context,id,'artifact'),/TICKET_IDENTITY_MISMATCH/);
    substitute=false;cancelled=true;const stopped=await getHostedTranslationJob(context,id);
    assert.equal(stopped.status,'CANCELLED');assert.equal(stopped.artifactReady,false);assert.equal(stopped.reportReady,true);
    await assert.rejects(hostedTranslationArtifactTicket(context,id,'artifact'),/NOT_READY/);
  });
