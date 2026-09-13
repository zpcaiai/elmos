/**
 * @file miniapp-subpackage-optimizer.ts
 * @description MiniApp Subpackage & Independent Subpackage Dependency Optimizer.
 * Analyzes page and component dependency graphs, extracts shared utilities to the main package,
 * partitions feature modules into subpackages (subPackages in app.json),
 * tags independent subpackages, and generates preloadRule pre-fetching configurations.
 */

export interface PageDescriptor {
  path: string; // e.g. "pages/index/index"
  dependencies: string[]; // imported component or util paths
  isEntryPage?: boolean;
  isTabBarPage?: boolean;
  subpackageHint?: string; // e.g. "packageWms"
  isIndependent?: boolean;
}

export interface SubpackageConfig {
  root: string;
  name?: string;
  pages: string[];
  independent?: boolean;
}

export interface PreloadRule {
  [pagePath: string]: {
    packages: string[];
    network?: 'all' | 'wifi';
  };
}

export interface OptimizedAppStructure {
  mainPackagePages: string[];
  subPackages: SubpackageConfig[];
  preloadRules: PreloadRule;
  sharedMainPackageModules: string[];
}

export class MiniAppSubpackageOptimizer {
  private pages: Map<string, PageDescriptor> = new Map();

  public registerPage(page: PageDescriptor): void {
    this.pages.set(page.path, page);
  }

  /**
   * Optimizes the app packaging structure into main package and feature subpackages
   */
  public optimize(): OptimizedAppStructure {
    const mainPackagePages: string[] = [];
    const subpackageMap: Map<string, SubpackageConfig> = new Map();
    const preloadRules: PreloadRule = {};

    // 1. Dependency frequency analysis for shared module lifting
    const moduleUsageCount: Map<string, number> = new Map();
    for (const page of this.pages.values()) {
      for (const dep of page.dependencies) {
        moduleUsageCount.set(dep, (moduleUsageCount.get(dep) || 0) + 1);
      }
    }

    const sharedMainPackageModules: string[] = [];
    for (const [mod, count] of moduleUsageCount.entries()) {
      if (count > 1) {
        sharedMainPackageModules.push(mod);
      }
    }

    // 2. Partition pages into main package or subpackages
    for (const page of this.pages.values()) {
      // TabBar and entry pages MUST reside in main package
      if (page.isEntryPage || page.isTabBarPage || !page.subpackageHint) {
        mainPackagePages.push(page.path);
        continue;
      }

      // Assign to subpackage
      const subRoot = page.subpackageHint;
      let subConfig = subpackageMap.get(subRoot);
      if (!subConfig) {
        subConfig = {
          root: subRoot,
          name: subRoot.replace(/[^a-zA-Z0-9]/g, ''),
          pages: [],
          independent: page.isIndependent ?? false,
        };
        subpackageMap.set(subRoot, subConfig);
      }

      // Page path inside subpackage is relative to subRoot
      const relativePagePath = page.path.startsWith(subRoot + '/')
        ? page.path.substring(subRoot.length + 1)
        : page.path;
      subConfig.pages.push(relativePagePath);
    }

    // 3. Generate preload rules for smooth user experience
    // E.g. when entering main page "pages/dashboard/index", preload the most used subpackage
    for (const sub of subpackageMap.values()) {
      if (!sub.independent) {
        preloadRules['pages/index/index'] = {
          packages: [sub.root],
          network: 'all',
        };
      }
    }

    return {
      mainPackagePages,
      subPackages: Array.from(subpackageMap.values()),
      preloadRules,
      sharedMainPackageModules,
    };
  }

  /**
   * Generates app.json snippet with subPackages and preloadRule
   */
  public generateAppJsonSnippet(optimized: OptimizedAppStructure): Record<string, any> {
    return {
      pages: optimized.mainPackagePages,
      subPackages: optimized.subPackages,
      preloadRule: optimized.preloadRules,
    };
  }
}
