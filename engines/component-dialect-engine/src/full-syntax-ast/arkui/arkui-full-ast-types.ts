/**
 * Complete AST type definitions for HarmonyOS ArkTS / ArkUI 3.0 Declarative UI.
 * 
 * Accurately models ArkTS component hierarchy, decorators, state management,
 * layout containers, atomic components, style modifiers, gestures, animations,
 * and component lifecycle hooks.
 */

export type ArkUIDecoratorKind =
  | "@Component"
  | "@Entry"
  | "@Preview"
  | "@CustomDialog"
  | "@State"
  | "@Prop"
  | "@Link"
  | "@Provide"
  | "@Consume"
  | "@Observed"
  | "@ObjectLink"
  | "@Watch"
  | "@StorageLink"
  | "@StorageProp"
  | "@LocalStorageLink"
  | "@LocalStorageProp"
  | "@Builder"
  | "@BuilderParam"
  | "@Styles"
  | "@Extend";

export interface ArkUIDecorator {
  kind: ArkUIDecoratorKind;
  arguments?: string[];
}

export interface ArkUIStateProperty {
  name: string;
  decorator: ArkUIDecorator;
  typeAnnotation: string;
  initialValueExpr?: string;
  watchCallbackName?: string;
}

export interface ArkUIBuilderParam {
  name: string;
  typeAnnotation: string;
  required: boolean;
  defaultBuilderName?: string;
}

export interface ArkUIBuilderMethod {
  name: string;
  parameters: { name: string; type: string }[];
  body: ArkUINode[];
}

export interface ArkUIStylesMethod {
  name: string;
  modifiers: ArkUIModifier[];
}

export interface ArkUIExtendMethod {
  targetComponent: string;
  name: string;
  parameters: { name: string; type: string }[];
  modifiers: ArkUIModifier[];
}

export type ArkUIContainerComponent =
  | "Column"
  | "Row"
  | "Stack"
  | "Flex"
  | "Grid"
  | "GridItem"
  | "List"
  | "ListItem"
  | "ListItemGroup"
  | "Scroll"
  | "Swiper"
  | "Tabs"
  | "TabContent"
  | "SideBarContainer"
  | "RelativeContainer"
  | "WaterFlow"
  | "FlowItem"
  | "Refresh";

export type ArkUIAtomicComponent =
  | "Text"
  | "Button"
  | "Image"
  | "TextInput"
  | "TextArea"
  | "Toggle"
  | "Checkbox"
  | "CheckboxGroup"
  | "Radio"
  | "RadioGroup"
  | "Select"
  | "Slider"
  | "Rating"
  | "Progress"
  | "LoadingProgress"
  | "Badge"
  | "Divider"
  | "Span"
  | "ImageSpan"
  | "Search"
  | "Menu"
  | "MenuItem"
  | "MenuItemGroup"
  | "DatePicker"
  | "TimePicker"
  | "TextPicker"
  | "Gauge"
  | "QRCode"
  | "Marquee"
  | "AlphabetIndexer";

export type ArkUINodeKind =
  | "container"
  | "atomic"
  | "custom_component"
  | "builder_invocation"
  | "conditional_if"
  | "loop_for_each"
  | "lazy_for_each";

export interface ArkUIModifier {
  name: string; // e.g. 'width', 'height', 'fontSize', 'backgroundColor', 'onClick'
  args: string[];
  isEvent?: boolean;
}

export interface ArkUIGestureBinding {
  gestureKind:
    | "TapGesture"
    | "LongPressGesture"
    | "PanGesture"
    | "PinchGesture"
    | "RotationGesture"
    | "SwipeGesture"
    | "GestureGroup";
  priority?: "Normal" | "Parallel" | "Exclusive";
  parameters?: Record<string, string | number>;
  onActionHandler?: string;
  onActionEndHandler?: string;
  onActionCancelHandler?: string;
}

export interface ArkUIAnimationParam {
  duration?: number;
  curve?: "Linear" | "Ease" | "EaseIn" | "EaseOut" | "EaseInOut" | "FastOutSlowIn" | "springMotion";
  delay?: number;
  iterations?: number;
  playMode?: "Normal" | "Reverse" | "Alternate" | "AlternateReverse";
  tempo?: number;
  onFinish?: string;
}

export interface ArkUINode {
  id: string;
  kind: ArkUINodeKind;
  componentName: string; // 'Column', 'Text', 'MyCustomComp', etc.
  constructorArgs?: string[];
  modifiers: ArkUIModifier[];
  gestures?: ArkUIGestureBinding[];
  animation?: ArkUIAnimationParam;
  children?: ArkUINode[];
  
  // Conditional control flow (If / ElseIf / Else)
  conditionBranches?: {
    testExpr?: string; // undefined for final 'else'
    children: ArkUINode[];
  }[];

  // List iteration control flow (ForEach / LazyForEach)
  forEach?: {
    isLazy: boolean;
    arrayExpr: string;
    itemParam: string;
    indexParam?: string;
    keyGeneratorExpr?: string;
    template: ArkUINode[];
  };

  // Builder param projection
  builderParamName?: string;
}

export interface ArkUILifecycleMethod {
  name:
    | "aboutToAppear"
    | "aboutToDisappear"
    | "onPageShow"
    | "onPageHide"
    | "onBackPress";
  bodyCode: string;
}

export interface ArkUIComponentAst {
  structName: string;
  isEntry: boolean;
  isPreview: boolean;
  stateProperties: ArkUIStateProperty[];
  builderParams: ArkUIBuilderParam[];
  builderMethods: ArkUIBuilderMethod[];
  stylesMethods: ArkUIStylesMethod[];
  extendMethods: ArkUIExtendMethod[];
  lifecycleMethods: ArkUILifecycleMethod[];
  customMethods: {
    name: string;
    parameters: { name: string; type: string; defaultValue?: string }[];
    returnType: string;
    bodyCode: string;
    isAsync: boolean;
  }[];
  buildRoot: ArkUINode;
  importedModules: {
    namedImports: string[];
    defaultImport?: string;
    moduleSpecifier: string;
  }[];
}
