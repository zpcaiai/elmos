import { FullSyntaxComponentIR, SourceFramework, TargetFramework, TranspilationResult } from "./types";
import { ReactFullAstParser } from "./parsers/react-full-ast-parser";
import { Vue3FullAstParser } from "./parsers/vue3-full-ast-parser";
import { Vue2FullAstParser } from "./parsers/vue2-full-ast-parser";
import { AngularFullAstParser } from "./parsers/angular-full-ast-parser";
import { SvelteFullAstParser } from "./parsers/svelte-full-ast-parser";
import { MiniAppFullAstParser, MiniAppFiles } from "./parsers/miniapp-full-ast-parser";
import { UniversalIrTransformer } from "./transformers/universal-ir-transformer";
import { Vue3FullAstEmitter } from "./emitters/vue3-full-ast-emitter";
import { ReactFullAstEmitter } from "./emitters/react-full-ast-emitter";
import { MiniAppFullAstEmitter } from "./emitters/miniapp-full-ast-emitter";

export interface TranspileOptions {
  componentNameHint?: string;
  sourceFiles?: MiniAppFiles; // For MiniApp multi-file source
}

export class FullSyntaxFrontendTranspiler {
  private reactParser = new ReactFullAstParser();
  private vue3Parser = new Vue3FullAstParser();
  private vue2Parser = new Vue2FullAstParser();
  private angularParser = new AngularFullAstParser();
  private svelteParser = new SvelteFullAstParser();
  private miniappParser = new MiniAppFullAstParser();

  private transformer = new UniversalIrTransformer();

  private vue3Emitter = new Vue3FullAstEmitter();
  private reactEmitter = new ReactFullAstEmitter();
  private miniappEmitter = new MiniAppFullAstEmitter();

  /**
   * Parse any of the 6 major source frameworks into FullSyntaxComponentIR.
   */
  public parseToIr(
    source: string | MiniAppFiles,
    sourceFramework: SourceFramework,
    componentNameHint?: string
  ): FullSyntaxComponentIR {
    switch (sourceFramework) {
      case "react":
        return this.reactParser.parse(typeof source === "string" ? source : source.js, componentNameHint);
      case "vue3":
        return this.vue3Parser.parse(typeof source === "string" ? source : source.js, componentNameHint);
      case "vue2":
        return this.vue2Parser.parse(typeof source === "string" ? source : source.js, componentNameHint);
      case "angular":
        return this.angularParser.parse(typeof source === "string" ? source : source.js, componentNameHint);
      case "svelte":
        return this.svelteParser.parse(typeof source === "string" ? source : source.js, componentNameHint);
      case "miniprogram":
        return this.miniappParser.parse(source, componentNameHint);
      default:
        throw new Error(`Unsupported source framework: ${sourceFramework}`);
    }
  }

  /**
   * Transpile source code from any of 6 frameworks to target framework.
   */
  public transpile(
    source: string | MiniAppFiles,
    sourceFramework: SourceFramework,
    targetFramework: TargetFramework,
    options: TranspileOptions = {}
  ): TranspilationResult {
    const diagnostics: string[] = [];

    // 1. Parse source AST into unified IR
    const rawIr = this.parseToIr(source, sourceFramework, options.componentNameHint);

    // 2. Transform IR for target framework
    const targetIr = this.transformer.transform(rawIr, targetFramework);

    // 3. Emit target code
    let outputFiles: Record<string, string> = {};
    switch (targetFramework) {
      case "vue3":
        outputFiles = this.vue3Emitter.emit(targetIr);
        break;
      case "react":
        outputFiles = this.reactEmitter.emit(targetIr);
        break;
      case "miniapp":
      case "miniprogram":
        outputFiles = this.miniappEmitter.emit(targetIr);
        break;
      default:
        diagnostics.push(`Target framework ${targetFramework} fallback to standard React TSX`);
        outputFiles = this.reactEmitter.emit(targetIr);
        break;
    }

    return {
      componentName: targetIr.componentName,
      sourceFramework,
      targetFramework,
      success: true,
      outputFiles,
      diagnostics,
      ir: targetIr,
    };
  }
}
