// Read-only local engineering replay. Never starts the Python pipeline/provider.
import path from 'node:path';
import { realpath } from 'node:fs/promises';
import { stableDocumentBytes } from './entrypoint.mjs';
import { validateTranslationPreflight } from '../web-console/app/lib/server/translationConversionReport.ts';
import { validateCompletedTranslationPipeline } from '../web-console/app/lib/server/translationRunner.ts';
if(!process.argv[2] || !path.isAbsolute(process.argv[2]))throw new Error('ABSOLUTE_LOCAL_FIXTURE_REQUIRED');
const root=await realpath(process.argv[2]);
const request=JSON.parse((await stableDocumentBytes(path.join(root,'input/request.json'))).toString('utf8'));
const preflight=validateTranslationPreflight(JSON.parse((await stableDocumentBytes(path.join(root,'output/gate/preflight.json'))).toString('utf8')),
  {repositoryRef:request.repositoryRef,routeId:`${request.sourceLanguage}-to-${request.targetLanguage}`,
    sourceLanguage:request.sourceLanguage,targetLanguage:request.targetLanguage});
const verified=await validateCompletedTranslationPipeline(path.join(root,'temporary/pipeline'),request,preflight);
console.log(JSON.stringify({schemaVersion:'translation-local-replay-v1',status:verified.status,
  artifactSha256:verified.verifiedArtifact?.sha256,artifactBytes:verified.verifiedArtifact?.size,
  manifestSha256:verified.verifiedManifestSha256,repositoryComplete:verified.report.repository_complete,
  independentVerification:'NOT_RUN',externalVerification:'NOT_RUN',certificationStatus:'NOT_CERTIFIED'},null,2));
