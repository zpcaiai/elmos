import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { mkdir, open, realpath, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { validateCompletedTranslationPipeline } from '../web-console/app/lib/server/translationRunner.ts';
import { validateTranslationPreflight } from '../web-console/app/lib/server/translationConversionReport.ts';

export async function stableDocumentBytes(file, maximum = 2 * 1024 * 1024) {
  const handle=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW);
  try {
    const before=await handle.stat();
    if (!before.isFile() || before.size<1 || before.size>maximum) throw new Error('TRANSLATION_LAUNCHER_DOCUMENT_INVALID');
    const bytes=Buffer.alloc(before.size);let offset=0;
    while(offset<bytes.length) {
      const result=await handle.read(bytes,offset,bytes.length-offset,offset);
      if(result.bytesRead===0) throw new Error('TRANSLATION_LAUNCHER_DOCUMENT_CHANGED');offset+=result.bytesRead;
    }
    const after=await handle.stat();
    if(before.size!==after.size || before.ino!==after.ino || before.dev!==after.dev || before.mtimeMs!==after.mtimeMs || before.ctimeMs!==after.ctimeMs)
      throw new Error('TRANSLATION_LAUNCHER_DOCUMENT_CHANGED');
    return bytes;
  } finally {await handle.close();}
}
async function document(file,maximum) {return JSON.parse((await stableDocumentBytes(file,maximum)).toString('utf8'));}
async function copyVerified(source, target, descriptor) {
  await mkdir(path.dirname(target), { recursive: true });
  const sourceHandle=await open(source,constants.O_RDONLY|constants.O_NOFOLLOW);
  try {
    const before=await sourceHandle.stat();
    if(!before.isFile() || before.size!==descriptor.bytes)throw new Error('TRANSLATION_OUTPUT_COPY_INTEGRITY_MISMATCH');
    const output=await open(target,'wx',0o600);
    try {
      const buffer=Buffer.alloc(64*1024),hash=createHash('sha256');let total=0;
      for(;;) {
        const {bytesRead}=await sourceHandle.read(buffer,0,buffer.length,total);if(!bytesRead)break;
        total+=bytesRead;if(total>descriptor.bytes)throw new Error('TRANSLATION_OUTPUT_COPY_INTEGRITY_MISMATCH');
        hash.update(buffer.subarray(0,bytesRead));let offset=0;
        while(offset<bytesRead){const written=await output.write(buffer,offset,bytesRead-offset);if(!written.bytesWritten)throw new Error('TRANSLATION_OUTPUT_COPY_STALLED');offset+=written.bytesWritten;}
      }
      const after=await sourceHandle.stat();
      if(total!==descriptor.bytes || hash.digest('hex')!==descriptor.sha256 || before.size!==after.size
        || before.mtimeMs!==after.mtimeMs || before.ctimeMs!==after.ctimeMs)throw new Error('TRANSLATION_OUTPUT_COPY_INTEGRITY_MISMATCH');
      await output.sync();
    } finally {await output.close();}
  } finally {await sourceHandle.close();}
}
async function run(python, args, cwd) {
  await new Promise((resolve, reject) => {
    const child = spawn(python, ['-m', 'elmos_polyglot_route.cli', ...args], { cwd, stdio: ['ignore', 'inherit', 'inherit'], shell: false });
    child.once('error', reject);
    child.once('close', (code, signal) => code === 0 ? resolve() : reject(new Error(`TRANSLATION_ENGINE_EXIT_${signal ?? code}`)));
  });
}

/** Phase is supplied by the lease-owning Runner, never by repository input. */
export async function runTranslationPhase({ phase, inputDir, outputDir, temporaryDir, python }) {
  if (!['translate-preflight-v1', 'translate-pipeline-v1'].includes(phase)) throw new Error('TRANSLATION_LAUNCHER_PHASE_INVALID');
  for (const directory of [inputDir, outputDir, temporaryDir]) {
    if (!path.isAbsolute(directory) || await realpath(directory) !== directory) throw new Error('TRANSLATION_LAUNCHER_DIRECTORY_INVALID');
  }
  if (!path.isAbsolute(python)) throw new Error('TRANSLATION_PYTHON_ABSOLUTE_REQUIRED');
  const request = await document(path.join(inputDir, 'request.json'));
  const manifest = await document(path.join(inputDir, 'manifest.json'), 4 * 1024 * 1024);
  for (const field of ['schemaVersion','tenantId','actor','repositoryWorkspaceId','repositoryRef','sourceCommit','sourceLanguage','targetLanguage','casesBundleId']) {
    if (typeof request[field] !== 'string' || request[field] !== manifest[field]) throw new Error('TRANSLATION_LAUNCHER_SUBJECT_INVALID');
  }
  if (request.schemaVersion !== 'translation-input-v1' || !/^[a-f0-9]{64}$/.test(request.input?.sha256)) throw new Error('TRANSLATION_LAUNCHER_INPUT_INVALID');
  const common = ['--repository', path.join(inputDir,'source'), '--repository-ref',request.repositoryRef,
    '--source-language',request.sourceLanguage,'--target-language',request.targetLanguage];
  const preflightPath = path.join(outputDir,'preflight.json');
  if (phase === 'translate-preflight-v1') {
    await run(python,['repository-preflight',...common,'--output',preflightPath],temporaryDir);
    const checked = validateTranslationPreflight(await document(preflightPath), {
      repositoryRef:request.repositoryRef, routeId:`${request.sourceLanguage}-to-${request.targetLanguage}`,
      sourceLanguage:request.sourceLanguage,targetLanguage:request.targetLanguage,
    });
    if (checked.status === 'REJECTED') throw new Error('TRANSLATION_PREFLIGHT_REJECTED');
    return checked;
  }
  const preflightBytes=await stableDocumentBytes(preflightPath);
  const preflight = validateTranslationPreflight(JSON.parse(preflightBytes.toString('utf8')), {
    repositoryRef:request.repositoryRef,routeId:`${request.sourceLanguage}-to-${request.targetLanguage}`,
    sourceLanguage:request.sourceLanguage,targetLanguage:request.targetLanguage,
  });
  if (preflight.status === 'REJECTED') throw new Error('TRANSLATION_PREFLIGHT_REJECTED');
  const pipeline = path.join(temporaryDir,'pipeline');
  await run(python,['repository-pipeline',...common,'--cases-directory',path.join(inputDir,'cases'),'--output',pipeline],temporaryDir);
  const verified = await validateCompletedTranslationPipeline(pipeline,request,preflight);
  const { conversion, report, verifiedArtifact, status } = verified;
  const outputs = [
    ['reports/functional-conversion-report.json', conversion.jsonReport],
    ['reports/FUNCTION_CONVERSION_REPORT.md', conversion.markdownReport],
    ...(conversion.reportBundle ? [['evidence/FUNCTION_CONVERSION_REPORT_BUNDLE.zip', conversion.reportBundle]] : []),
  ];
  for (const [name, descriptor] of outputs) await copyVerified(path.join(pipeline, descriptor.path), path.join(outputDir,name),descriptor);
  if (verifiedArtifact) await copyVerified(verifiedArtifact.path,path.join(outputDir,'repository-migration-artifact.zip'),{
    bytes:verifiedArtifact.size,sha256:verifiedArtifact.sha256,
  });
  await mkdir(path.join(outputDir,'gate'),{recursive:true});
  // Preserve exactly the receipt used before pipeline execution. The writable
  // output mount may have been changed by the pipeline in the meantime.
  await writeFile(path.join(outputDir,'gate/preflight.json'),preflightBytes,{flag:'wx',mode:0o600});
  await unlink(preflightPath);
  const result = {
    schemaVersion:'translation-hosted-result-v1',tenantId:request.tenantId,inputSha256:request.input.sha256,
    repositoryRef:request.repositoryRef,sourceLanguage:request.sourceLanguage,targetLanguage:request.targetLanguage,
    status,snapshotSha256:report.snapshot_sha256,conversionSummary:conversion.summary,functionalConversion:report.functional_conversion,
    readyCount:verified.readyCount,workUnitCount:verified.workUnitCount,includedUnitCount:verified.includedUnitCount,
    statusCounts:verified.batchCounts,buildVerification:verified.buildVerification,
    artifactReady:conversion.summary.codeArtifactReady,reportReady:true,
    reportJson:conversion.jsonReport,reportMarkdown:conversion.markdownReport,reportBundle:conversion.reportBundle,
    artifactSha256:verifiedArtifact?.sha256,artifactSize:verifiedArtifact?.size,
    artifactManifestSha256:verified.verifiedManifestSha256,semanticCoverage:verified.semanticCoverage,
    behaviorCoverage:verified.behaviorCoverage,repositoryComplete:report.repository_complete,
    independentVerification:'NOT_RUN',externalCertification:'NOT_RUN',certificationStatus:'NOT_CERTIFIED',
    ...(status === 'BLOCKED' ? {reason:verified.packagingReasonCode ?? report.reason ?? 'TRANSLATION_PIPELINE_REPORTED_BLOCKED'} : {}),
  };
  await writeFile(path.join(outputDir,'gate/translation-job.json'),JSON.stringify(result),{flag:'wx',mode:0o600});
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runTranslationPhase({ phase:process.env.ELMOS_JOB_KIND,inputDir:process.env.ELMOS_INPUT_DIR,
    outputDir:process.env.ELMOS_OUTPUT_DIR,temporaryDir:'/elmos/tmp',python:'/opt/elmos/venv/bin/python' });
}
