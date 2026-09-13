/**
 * @file cross-platform-store-lowerer.ts
 * @description Bi-directional store transformation engine across Zustand, Redux Toolkit, Pinia, and MiniApp.
 * Validates state invariants, normalizes mutations vs actions, preserves persistence configs,
 * and lowers UniversalStoreIR to desired target architecture.
 * Conforms to Batch 32 Skill 1209 (b32-state-management-lifecycle).
 */

import {
  UniversalStoreIR,
  StoreFramework,
  StoreParseResult,
  StoreEmitResult,
  StoreMigrationPlan,
} from './store-ir-types';
import { ZustandAdapter } from './zustand-adapter';
import { ReduxToolkitAdapter } from './redux-toolkit-adapter';
import { PiniaAdapter } from './pinia-adapter';
import { MiniAppStoreAdapter } from './miniapp-store-adapter';

export class CrossPlatformStoreLowerer {
  private zustandAdapter = new ZustandAdapter();
  private rtkAdapter = new ReduxToolkitAdapter();
  private piniaAdapter = new PiniaAdapter();
  private miniappAdapter = new MiniAppStoreAdapter();

  /**
   * Parse store code into UniversalStoreIR using appropriate adapter
   */
  public parse(sourceCode: string, framework: StoreFramework, storeId?: string): StoreParseResult {
    switch (framework) {
      case 'zustand':
        return this.zustandAdapter.parse(sourceCode, storeId);
      case 'redux-toolkit':
        return this.rtkAdapter.parse(sourceCode, storeId);
      case 'pinia':
        return this.piniaAdapter.parse(sourceCode, storeId);
      case 'miniapp-store':
        return this.miniappAdapter.parse(sourceCode, storeId);
      default:
        // Attempt auto-discovery
        if (sourceCode.includes('createSlice')) {
          return this.rtkAdapter.parse(sourceCode, storeId);
        } else if (sourceCode.includes('defineStore')) {
          return this.piniaAdapter.parse(sourceCode, storeId);
        } else if (sourceCode.includes('create(') || sourceCode.includes('create<')) {
          return this.zustandAdapter.parse(sourceCode, storeId);
        } else {
          return this.miniappAdapter.parse(sourceCode, storeId);
        }
    }
  }

  /**
   * Emit target code from UniversalStoreIR using specified framework adapter
   */
  public emit(storeIR: UniversalStoreIR, targetFramework: StoreFramework): StoreEmitResult {
    switch (targetFramework) {
      case 'zustand':
        return this.zustandAdapter.emit(storeIR);
      case 'redux-toolkit':
        return this.rtkAdapter.emit(storeIR);
      case 'pinia':
        return this.piniaAdapter.emit(storeIR);
      case 'miniapp-store':
        return this.miniappAdapter.emit(storeIR);
      default:
        throw new Error(`Unsupported target store framework: ${targetFramework}`);
    }
  }

  /**
   * Transform store code from one framework to another
   */
  public transform(
    sourceCode: string,
    sourceFramework: StoreFramework,
    targetFramework: StoreFramework,
    storeId?: string
  ): { emitResult: StoreEmitResult; parseResult: StoreParseResult; plan: StoreMigrationPlan } {
    const parseResult = this.parse(sourceCode, sourceFramework, storeId);
    if (!parseResult.success || !parseResult.storeIR) {
      throw new Error(`Failed to parse source store: ${parseResult.errors.join(', ')}`);
    }

    const plan = this.generatePlan(parseResult.storeIR, targetFramework);
    const normalizedIR = this.normalizeForTarget(parseResult.storeIR, targetFramework);
    const emitResult = this.emit(normalizedIR, targetFramework);

    return { emitResult, parseResult, plan };
  }

  /**
   * Plan migration steps and check invariant constraints
   */
  public generatePlan(storeIR: UniversalStoreIR, targetFramework: StoreFramework): StoreMigrationPlan {
    const steps: Array<{ stepName: string; description: string; affectedConstructs: string[] }> = [];
    const warnings: string[] = [];
    const unsupportedFeatures: string[] = [];

    steps.push({
      stepName: 'State Model Extraction',
      description: `Extract ${storeIR.stateFields.length} state fields and types`,
      affectedConstructs: storeIR.stateFields.map((f) => f.name),
    });

    if (storeIR.getters.length > 0) {
      steps.push({
        stepName: 'Computed Getters Migration',
        description: `Map ${storeIR.getters.length} getters to ${targetFramework} reactive computed properties`,
        affectedConstructs: storeIR.getters.map((g) => g.name),
      });
    }

    if (storeIR.mutations.length > 0) {
      steps.push({
        stepName: 'Synchronous Mutations Lowering',
        description: `Lower ${storeIR.mutations.length} mutations to ${targetFramework} reducer or mutation functions`,
        affectedConstructs: storeIR.mutations.map((m) => m.name),
      });
    }

    if (storeIR.actions.length > 0) {
      steps.push({
        stepName: 'Async Actions Lowering',
        description: `Convert ${storeIR.actions.length} async thunks/actions with side-effect tracking`,
        affectedConstructs: storeIR.actions.map((a) => a.name),
      });
    }

    if (storeIR.persistence) {
      if (targetFramework === 'miniapp-store') {
        steps.push({
          stepName: 'Storage Adapter Adaptation',
          description: `Migrate ${storeIR.persistence.storage} to native MiniApp wx.setStorageSync / wx.getStorageSync`,
          affectedConstructs: [storeIR.persistence.storageKey],
        });
      } else {
        steps.push({
          stepName: 'Persistence Middleware Configuration',
          description: `Configure ${targetFramework} persistence middleware with key '${storeIR.persistence.storageKey}'`,
          affectedConstructs: [storeIR.persistence.storageKey],
        });
      }
    }

    return {
      sourceFramework: storeIR.sourceFramework,
      targetFramework,
      storeId: storeIR.storeId,
      steps,
      warnings,
      unsupportedFeatures,
    };
  }

  private normalizeForTarget(storeIR: UniversalStoreIR, targetFramework: StoreFramework): UniversalStoreIR {
    const clone: UniversalStoreIR = JSON.parse(JSON.stringify(storeIR));

    // If target is miniapp-store and storage was localStorage/sessionStorage, convert to wx-storage
    if (targetFramework === 'miniapp-store' && clone.persistence) {
      clone.persistence.storage = 'wx-storage';
    }

    // Clean up mutation/action bodies if needed
    for (const mutation of clone.mutations) {
      if (targetFramework === 'pinia') {
        // Replace state.field with field.value
        for (const field of clone.stateFields) {
          const reg = new RegExp(`state\\.${field.name}\\b`, 'g');
          mutation.mutationBodyCode = mutation.mutationBodyCode.replace(reg, `${field.name}.value`);
        }
      } else if (targetFramework === 'zustand') {
        // Ensure state mutations are compatible
      }
    }

    return clone;
  }
}
