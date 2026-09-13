import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, realpath, rm, symlink } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { runTranslationPhase, stableDocumentBytes } from '../entrypoint.mjs';
import { validateCompletedTranslationPipeline } from '../../web-console/app/lib/server/translationRunner.ts';

test('launcher rejects an untrusted phase before spawning anything',async()=>{
  await assert.rejects(runTranslationPhase({phase:'arbitrary-shell'}),/PHASE_INVALID/);
});

test('launcher pins bounded document bytes and rejects links or oversized receipts',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'elmos-document-'));const file=path.join(root,'receipt.json');
  try {
    await writeFile(file,'{"status":"PASSED"}');const captured=await stableDocumentBytes(file);
    await writeFile(file,'{"status":"REPLACED"}');
    assert.equal(captured.toString(),' {"status":"PASSED"}'.trim());
    await symlink(file,path.join(root,'link.json'));await assert.rejects(stableDocumentBytes(path.join(root,'link.json')));
    await writeFile(file,Buffer.alloc(2*1024*1024+1));await assert.rejects(stableDocumentBytes(file),/DOCUMENT_INVALID/);
  } finally {await rm(root,{recursive:true,force:true});}
});

test('real Python to TypeScript fixture traverses both phases and full artifact validator',
  {skip:!process.env.ELMOS_TRANSLATION_TEST_PYTHON,timeout:3_600_000},async()=>{
    const root=await realpath(await mkdtemp(path.join(os.tmpdir(),'elmos-translation-launcher-')));
    const inputDir=path.join(root,'input'),outputDir=path.join(root,'output'),temporaryDir=path.join(root,'temporary');
    console.log(`TRANSLATION_REAL_FIXTURE_RETAINED=${root}`);
    try {
      for(const dir of [path.join(inputDir,'source/src'),path.join(inputDir,'cases'),outputDir,temporaryDir]) await mkdir(dir,{recursive:true});
      await writeFile(path.join(inputDir,'source/src/math.py'),'def add(left: int, right: int) -> int:\n    return left + right\n');
      await writeFile(path.join(inputDir,'cases/WU-00001.json'),JSON.stringify([{args:[2,3],expected:5}]));
      const subject={schemaVersion:'translation-input-v1',tenantId:'tenant-fixture',actor:'actor-fixture',
        repositoryWorkspaceId:'fixture',repositoryRef:'local:translation-launcher-fixture',sourceCommit:'a'.repeat(40),
        sourceLanguage:'python',targetLanguage:'typescript',casesBundleId:'cases-fixture'};
      await writeFile(path.join(inputDir,'manifest.json'),JSON.stringify(subject));
      await writeFile(path.join(inputDir,'request.json'),JSON.stringify({...subject,input:{sha256:'b'.repeat(64)}}));
      const config={inputDir,outputDir,temporaryDir,python:process.env.ELMOS_TRANSLATION_TEST_PYTHON};
      const preflight=await runTranslationPhase({...config,phase:'translate-preflight-v1'});
      assert.equal(preflight.status,'PASSED');
      const result=await runTranslationPhase({...config,phase:'translate-pipeline-v1'});
      assert.equal(result.status,'COMPLETE');
      assert.equal(result.artifactReady,true);
      assert.equal(result.certificationStatus,'NOT_CERTIFIED');
      assert.equal(result.independentVerification,'NOT_RUN');
      const persisted=JSON.parse(await readFile(path.join(outputDir,'gate/translation-job.json'),'utf8'));
      assert.deepEqual(persisted,JSON.parse(JSON.stringify(result)));
      assert.match(persisted.artifactSha256,/^[a-f0-9]{64}$/);
      const pipeline=path.join(temporaryDir,'pipeline');
      const manifestPath=path.join(pipeline,'artifact-manifest.json');
      const original=await readFile(manifestPath);const manifest=JSON.parse(original);
      for(const field of ['status','repository_ref','snapshot_sha256','route_id','profile','source_language','target_language',
        'repository_scale','repository_limits','unit_batch_status','project_graph','conversion_coverage','behavior_coverage',
        'repository_complete','runtime_verification_status','local_execution_evidence','repository_execution_status',
        'independent_verification_status','external_verification_status','certification_status']) {
        try {
          await writeFile(manifestPath,JSON.stringify({...manifest,[field]:null}));
          await assert.rejects(validateCompletedTranslationPipeline(pipeline,subject,preflight),undefined,`altered shared claim ${field}`);
        } finally {await writeFile(manifestPath,original);}
      }
      const graphPath=path.join(pipeline,'project-graph.json'),originalGraph=await readFile(graphPath);
      try {
        await writeFile(graphPath,JSON.stringify({...JSON.parse(originalGraph),nodes:[]}));
        await assert.rejects(validateCompletedTranslationPipeline(pipeline,subject,preflight),/PROJECT_GRAPH_DIGEST_INVALID/);
      } finally {await writeFile(graphPath,originalGraph);}
      await assert.rejects(validateCompletedTranslationPipeline(pipeline,subject,{...preflight,snapshotSha256:'0'.repeat(64)}));
      console.log('TRANSLATION_REAL_ARTIFACT_AND_22_NEGATIVE_REPLAYS_PASSED');
    } catch(error) {
      console.error(`TRANSLATION_REAL_FIXTURE_FAILURE_RETAINED=${root}`);throw error;
    }
  });
