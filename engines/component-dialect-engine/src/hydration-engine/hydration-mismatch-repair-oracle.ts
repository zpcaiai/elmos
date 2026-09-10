/**
 * @file hydration-mismatch-repair-oracle.ts
 * @description Hydration Mismatch Detection and Automated Repair Oracle.
 * Identifies root causes of SSR-to-client hydration mismatches (timestamps, random IDs,
 * browser-only globals like window/localStorage) and emits verified repairs.
 * Conforms to Batch 32 Skill 1213 (b32-rendering-ssr-csr-hydration).
 */

import {
  HydrationMismatchRecord,
  HydrationMismatchKind,
} from './hydration-ir-types';

export class HydrationMismatchRepairOracle {
  /**
   * Diagnose SSR vs Client DOM mismatch
   */
  public diagnose(
    domPath: string,
    serverValue: string,
    clientValue: string
  ): HydrationMismatchRecord {
    const kind = this.classifyMismatch(serverValue, clientValue);
    const id = `mismatch_${Math.random().toString(36).substring(2, 9)}`;

    let suggestedRepair: HydrationMismatchRecord['suggestedRepair'] = 'suppressHydrationWarning';
    let isFatal = false;
    let explanation = '';

    switch (kind) {
      case 'timestamp-drift':
        suggestedRepair = 'move-to-useEffect';
        isFatal = false;
        explanation = `Timestamp formatted on server ("${serverValue}") diverges from client local time ("${clientValue}"). Move time formatting to a client-side useEffect hook or pass a fixed ISO string from server.`;
        break;
      case 'random-id-mismatch':
        suggestedRepair = 'replace-with-stable-seed';
        isFatal = false;
        explanation = `Math.random() or uuid generated differing IDs ("${serverValue}" vs "${clientValue}"). Use React 18 useId() or deterministic counter.`;
        break;
      case 'client-only-node-missing':
        suggestedRepair = 'move-to-useEffect';
        isFatal = true;
        explanation = `Node rendered on client relies on browser globals (window/document/localStorage) not present on server. Wrap in an "isMounted" state flag.`;
        break;
      case 'server-tag-mismatch':
        suggestedRepair = 'suppressHydrationWarning';
        isFatal = true;
        explanation = `HTML tag divergence: server produced "${serverValue}" but client rendered "${clientValue}". Check for invalid HTML nesting (e.g. <div> inside <p>).`;
        break;
      case 'attribute-divergence':
        suggestedRepair = 'suppressHydrationWarning';
        isFatal = false;
        explanation = `Attribute mismatch between server ("${serverValue}") and client ("${clientValue}").`;
        break;
      default:
        suggestedRepair = 'suppressHydrationWarning';
        isFatal = false;
        explanation = `Text content mismatch between server and client.`;
        break;
    }

    return {
      id,
      kind,
      domPath,
      serverValue,
      clientValue,
      suggestedRepair,
      isFatal,
      explanation,
    };
  }

  private classifyMismatch(serverVal: string, clientVal: string): HydrationMismatchKind {
    // Check for date/time strings
    const dateRegex = /\d{4}[-/.]\d{2}[-/.]\d{2}|\d{1,2}:\d{2}(?::\d{2})?/;
    if (dateRegex.test(serverVal) && dateRegex.test(clientVal)) {
      return 'timestamp-drift';
    }

    // Check for random IDs
    const idRegex = /^[a-zA-Z0-9_-]{8,}$/;
    if (idRegex.test(serverVal) && idRegex.test(clientVal) && serverVal !== clientVal) {
      return 'random-id-mismatch';
    }

    // Check for tag mismatch
    if (serverVal.startsWith('<') && clientVal.startsWith('<')) {
      const serverTag = serverVal.match(/<([a-zA-Z0-9]+)/)?.[1];
      const clientTag = clientVal.match(/<([a-zA-Z0-9]+)/)?.[1];
      if (serverTag && clientTag && serverTag !== clientTag) {
        return 'server-tag-mismatch';
      }
    }

    if (!serverVal && clientVal) {
      return 'client-only-node-missing';
    }

    return 'text-content-divergence';
  }
}
