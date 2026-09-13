// Host-owned policy adapter, never a repository-provided hook or entrypoint.
import { readTranslationExecutionCapability } from '../web-console/app/lib/server/translationRoutes.ts';
const [source,target]=process.argv.slice(2);
const route=readTranslationExecutionCapability().routes.find(route=>route.source===source && route.target===target);
if (!route || route.localExecution!=='PASSED' || route.repositoryExecutionStatus!=='PASSED'
    || !route.repositoryProfile || !route.repositoryEvidenceRef || !route.repositoryEvidenceSha256 || !route.repositoryEvidenceBytes) {
  throw new Error('TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE');
}
process.stdout.write(JSON.stringify({repositoryExecutionStatus:'PASSED',repositoryProfile:route.repositoryProfile,
  repositoryEvidenceRef:route.repositoryEvidenceRef,repositoryEvidenceSha256:route.repositoryEvidenceSha256,
  repositoryEvidenceBytes:route.repositoryEvidenceBytes}));
