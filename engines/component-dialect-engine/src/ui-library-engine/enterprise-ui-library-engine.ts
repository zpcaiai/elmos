/**
 * @file enterprise-ui-library-engine.ts
 * @description Core UI Library Translation Engine.
 * Analyzes JSX/TSX and Template AST, transforms UI components between Ant Design,
 * Element Plus, Vant, and MiniApp components, remapping props, slots, events, and imports.
 * Conforms to Batch 32 Skills 1208 & 1217.
 */

import * as ts from 'typescript';
import {
  UILibraryId,
  ComponentMappingRule,
  UILibraryConversionResult,
  CanonicalComponentType,
} from './ui-library-types';
import { AntDesignAdapter } from './ant-design-adapter';
import { ElementPlusAdapter } from './element-plus-adapter';
import { VantTDesignAdapter } from './vant-tdesign-adapter';

export class EnterpriseUILibraryEngine {
  private allRules: ComponentMappingRule[] = [];
  private rulesByKey: Map<string, ComponentMappingRule> = new Map();

  constructor() {
    this.initRules();
  }

  private initRules() {
    this.allRules = [
      ...AntDesignAdapter.getAllRules(),
      ...ElementPlusAdapter.getAllRules(),
      ...VantTDesignAdapter.getAllRules(),
    ];
    for (const rule of this.allRules) {
      this.rulesByKey.set(`${rule.sourceLibrary}:${rule.sourceComponentName}:${rule.targetLibrary}`, rule);
    }
  }

  /**
   * Find mapping rule between source and target library
   */
  public findRule(sourceLib: UILibraryId, componentName: string, targetLib: UILibraryId): ComponentMappingRule | undefined {
    const directRule = this.rulesByKey.get(`${sourceLib}:${componentName}:${targetLib}`);
    if (directRule) {
      return directRule;
    }
    // Search all rules with alias tolerance (e.g. vant vs vant-weapp)
    for (const r of this.allRules) {
      if (r.sourceComponentName === componentName) {
        const srcMatch = r.sourceLibrary === sourceLib ||
          (sourceLib === 'vant-weapp' && r.sourceLibrary === 'vant') ||
          (sourceLib === 'vant' && r.sourceLibrary === 'vant-weapp');
        const tgtMatch = r.targetLibrary === targetLib ||
          (targetLib === 'vant-weapp' && r.targetLibrary === 'vant') ||
          (targetLib === 'vant' && r.targetLibrary === 'vant-weapp');
        if (srcMatch && tgtMatch) {
          return r;
        }
      }
    }
    return undefined;
  }

  /**
   * Translate JSX source code from source UI library to target UI library
   */
  public transformJSX(
    sourceCode: string,
    sourceLib: UILibraryId,
    targetLib: UILibraryId
  ): UILibraryConversionResult {
    const matchedComponents: Array<{ source: string; target: string; canonicalType: CanonicalComponentType }> = [];
    const addedImports: Array<{ module: string; imports: string[] }> = [];
    const removedImports: Array<{ module: string; imports: string[] }> = [];
    const warnings: string[] = [];

    const sourceFile = ts.createSourceFile(
      'component.tsx',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX
    );

    let transformedCode = sourceCode;

    // 1. Scan and replace JSX elements
    const visit = (node: ts.Node) => {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const tagName = node.tagName.getText(sourceFile);
        const rule = this.findRule(sourceLib, tagName, targetLib);

        if (rule) {
          matchedComponents.push({
            source: tagName,
            target: rule.targetComponentName,
            canonicalType: rule.canonicalType,
          });

          // Replace tag name
          const tagRegex = new RegExp(`<${tagName}\\b`, 'g');
          transformedCode = transformedCode.replace(tagRegex, `<${rule.targetComponentName}`);

          const closeTagRegex = new RegExp(`</${tagName}>`, 'g');
          transformedCode = transformedCode.replace(closeTagRegex, `</${rule.targetComponentName}>`);

          // Transform attributes/props
          for (const attr of node.attributes.properties) {
            if (ts.isJsxAttribute(attr)) {
              const attrName = attr.name.getText(sourceFile);
              const pRule = rule.props.find((p) => p.sourceProp === attrName);

              if (pRule) {
                if (pRule.transformType === 'rename') {
                  const attrRegex = new RegExp(`\\b${attrName}(?=[=\\s>/])`, 'g');
                  transformedCode = transformedCode.replace(attrRegex, `${pRule.targetProp}`);
                } else if (pRule.transformType === 'value-map' && pRule.valueTransform?.exactMatch) {
                  const attrVal = attr.initializer?.getText(sourceFile).replace(/['"{}]/g, '') || '';
                  const mappedVal = pRule.valueTransform.exactMatch[attrVal];
                  if (mappedVal !== undefined) {
                    const fullAttr = attr.getText(sourceFile);
                    transformedCode = transformedCode.replace(fullAttr, `${pRule.targetProp}="${mappedVal}"`);
                  }
                }
              }

              // Transform events
              const eRule = rule.events.find((e) => e.sourceEvent === attrName);
              if (eRule) {
                const eventRegex = new RegExp(`\\b${attrName}=`, 'g');
                transformedCode = transformedCode.replace(eventRegex, `${eRule.targetEvent}=`);
              }
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    // 2. Adjust imports
    if (sourceLib === 'ant-design' && targetLib === 'element-plus') {
      transformedCode = transformedCode.replace(/import\s*\{([^}]+)\}\s*from\s*['"]antd['"];?/g, (match, p1) => {
        const imports = p1.split(',').map((s: string) => s.trim()).filter(Boolean);
        removedImports.push({ module: 'antd', imports });
        const targetImports = imports.map((i: string) => `El${i}`);
        addedImports.push({ module: 'element-plus', imports: targetImports });
        return `import { ${targetImports.join(', ')} } from 'element-plus';`;
      });
    }

    return {
      transformedCode,
      matchedComponents,
      addedImports,
      removedImports,
      warnings,
    };
  }
}
