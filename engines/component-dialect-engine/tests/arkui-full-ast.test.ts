/**
 * @file arkui-full-ast.test.ts
 * @description Comprehensive Jest test suite for ArkUI / ArkTS 3.0 Full-Syntax AST parser,
 * semantic lowerer, and code emitter.
 * Conforms to Batch 32 Skill 1208 & 1217.
 */

import { ArkUIFullAstParser } from '../src/full-syntax-ast/arkui/arkui-full-ast-parser';
import { ArkUIFullAstEmitter } from '../src/full-syntax-ast/arkui/arkui-full-ast-emitter';
import { ArkUISemanticLowering } from '../src/full-syntax-ast/arkui/arkui-semantic-lowering';
import { ArkUIComponentAst, ArkUIStateProperty, ArkUIModifier, ArkUINode } from '../src/full-syntax-ast/arkui/arkui-full-ast-types';

describe('ArkUI / ArkTS 3.0 Full-Syntax AST Subsystem', () => {
  const parser = new ArkUIFullAstParser();
  const emitter = new ArkUIFullAstEmitter();
  const lowerer = new ArkUISemanticLowering();

  const sampleArkTS = `
@Component
export struct CounterCard {
  @State count: number = 0;
  @Prop title: string = 'Counter';
  @Link isActive: boolean;

  build() {
    Column({ space: 10 }) {
      Text(this.title)
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
        .fontColor('#1f2937');

      Text('Current value: ' + this.count)
        .fontSize(16)
        .margin({ top: 4, bottom: 4 });

      Row({ space: 8 }) {
        Button('Decrement')
          .type(ButtonType.Normal)
          .onClick(() => {
            this.count--;
          });

        Button('Increment')
          .type(ButtonType.Capsule)
          .backgroundColor('#2563eb')
          .onClick(() => {
            this.count++;
          });
      }
      .width('100%')
      .justifyContent(FlexAlign.Center);
    }
    .width('100%')
    .padding(16)
    .borderRadius(8)
    .backgroundColor('#ffffff');
  }
}
`;

  it('should successfully parse ArkTS @Component struct into ArkUIComponentAst', () => {
    const comp = parser.parse(sampleArkTS);
    expect(comp).toBeDefined();
    expect(comp.structName).toBe('CounterCard');

    // Validate state properties
    expect(comp.stateProperties.length).toBe(3);

    const countProp = comp.stateProperties.find((p: ArkUIStateProperty) => p.name === 'count');
    expect(countProp).toBeDefined();
    expect(countProp?.decorator.kind).toBe('@State');
    expect(countProp?.typeAnnotation).toBe('number');
    expect(countProp?.initialValueExpr).toBe('0');

    const titleProp = comp.stateProperties.find((p: ArkUIStateProperty) => p.name === 'title');
    expect(titleProp).toBeDefined();
    expect(titleProp?.decorator.kind).toBe('@Prop');

    const activeProp = comp.stateProperties.find((p: ArkUIStateProperty) => p.name === 'isActive');
    expect(activeProp).toBeDefined();
    expect(activeProp?.decorator.kind).toBe('@Link');
  });

  it('should parse declarative UI hierarchy and chain-call modifiers', () => {
    const comp = parser.parse(sampleArkTS);
    expect(comp.buildRoot).toBeDefined();

    const rootNode = comp.buildRoot;
    expect(rootNode.componentName).toBe('Column');
    expect(rootNode.children?.length).toBe(3); // Text, Text, Row

    // Check modifiers on root Column
    expect(rootNode.modifiers.some((m: ArkUIModifier) => m.name === 'width')).toBe(true);
    expect(rootNode.modifiers.some((m: ArkUIModifier) => m.name === 'padding')).toBe(true);
    expect(rootNode.modifiers.some((m: ArkUIModifier) => m.name === 'backgroundColor')).toBe(true);

    // Check Row child and nested buttons
    const rowNode = rootNode.children?.find((c: ArkUINode) => c.componentName === 'Row');
    expect(rowNode).toBeDefined();
    expect(rowNode?.children?.length).toBe(2);
    expect(rowNode?.children?.[0]?.componentName).toBe('Button');
    expect(rowNode?.children?.[1]?.componentName).toBe('Button');
  });

  it('should lift ArkUIComponentAst to Universal FullSyntaxComponentIR', () => {
    const arkComp = parser.parse(sampleArkTS);
    const universalIR = lowerer.liftToUniversal(arkComp);

    expect(universalIR.componentName).toBe('CounterCard');
    expect(universalIR.sourceFramework).toBe('arkui');
    expect(universalIR.states.length + universalIR.props.length).toBe(3);
    expect(universalIR.templateRoot).toBeDefined();
    expect(universalIR.templateRoot.tag).toBe('view');
  });

  it('should roundtrip Universal IR back to ArkUIComponentAst and emit valid ArkTS code', () => {
    const arkComp = parser.parse(sampleArkTS);
    const universalIR = lowerer.liftToUniversal(arkComp);
    const loweredArkComp = lowerer.lowerToArkUI(universalIR);

    expect(loweredArkComp.structName).toBe('CounterCard');

    const emittedArkTS = emitter.emit(loweredArkComp);
    expect(emittedArkTS).toContain('@Component');
    expect(emittedArkTS).toContain('struct CounterCard');
    expect(emittedArkTS).toContain('@State count: number = 0');
    expect(emittedArkTS).toContain('build()');
    expect(emittedArkTS).toContain('Column');
  });

  it('should parse complex ArkUI List and ListItem components', () => {
    const listArkTS = `
@Component
export struct TodoList {
  @State items: string[] = ['Task 1', 'Task 2'];

  build() {
    List({ space: 8 }) {
      ForEach(this.items, (item: string) => {
        ListItem() {
          Text(item)
            .fontSize(14)
            .fontColor('#374151');
        }
        .padding(12)
        .backgroundColor('#f3f4f6');
      })
    }
    .width('100%')
    .height('100%');
  }
}
`;

    const comp = parser.parse(listArkTS);
    expect(comp).toBeDefined();
    expect(comp.structName).toBe('TodoList');
    expect(comp.buildRoot.componentName).toBe('List');
  });
});
