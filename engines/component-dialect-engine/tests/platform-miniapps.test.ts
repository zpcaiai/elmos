import * as ts from "typescript";
import { emitPlatformMiniApp, MiniAppPlatform } from "../src/emitters/platform-miniapps";
import { parseReactComponent } from "../src/parsers/react";
import { validateSyntax } from "../src/validator";

const SOURCE = `
function Dashboard({ title, items, onDone }: { title: string; items: { id: number; name: string }[]; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  return (
    <section className="dashboard">
      <h2>{title}</h2>
      {count > 0 ? (<strong>ready</strong>) : (<em>idle</em>)}
      <ul>
        {items.map((item) => (<li><button onClick={() => { setCount(count + item.id); onDone(item.id); }}>{item.name}</button></li>))}
      </ul>
      <StatusChip label={title} />
    </section>
  );
}
`;

const CASES: readonly {
  platform: MiniAppPlatform;
  template: "wxml" | "axml" | "ttml" | "xhsml";
  style: "wxss" | "acss" | "ttss" | "css";
  prefix: "wx" | "a" | "tt" | "xhs";
  event: "bindtap" | "onTap";
}[] = [
  { platform: "wechat", template: "wxml", style: "wxss", prefix: "wx", event: "bindtap" },
  { platform: "alipay", template: "axml", style: "acss", prefix: "a", event: "onTap" },
  { platform: "douyin", template: "ttml", style: "ttss", prefix: "tt", event: "bindtap" },
  { platform: "xiaohongshu", template: "xhsml", style: "css", prefix: "xhs", event: "bindtap" },
];

function syntaxErrors(source: string): readonly ts.Diagnostic[] {
  return (ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  }).diagnostics ?? []).filter((diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error);
}

/** A bounded structural check, not a substitute for a platform compiler. */
function expectBalancedTemplate(source: string): void {
  const stack: string[] = [];
  for (const match of source.matchAll(/<\/?([a-z][a-z0-9-]*)(?:\s[^<>]*?)?\s*\/?>/g)) {
    const token = match[0];
    const tag = match[1] as string;
    if (token.startsWith("</")) {
      expect(stack.pop()).toBe(tag);
    } else if (!token.endsWith("/>")) {
      stack.push(tag);
    }
  }
  expect(stack).toEqual([]);
}

describe.each(CASES)("$platform native mini-app emitter", ({ platform, template, style, prefix, event }) => {
  const component = parseReactComponent(SOURCE, "Dashboard.tsx");

  it("emits the exact four platform files deterministically", () => {
    const first = emitPlatformMiniApp(component, platform);
    const second = emitPlatformMiniApp(component, platform);
    expect(second).toEqual(first);
    expect(first.templateExtension).toBe(template);
    expect(first.styleExtension).toBe(style);
    expect(Object.keys(first.files).sort()).toEqual([template, "js", "json", style].sort());
  });

  it("renders native directives, events, tags, list identity and component registration", () => {
    const files = emitPlatformMiniApp(component, platform).files;
    const markup = files[template] as string;
    expect(markup).toContain(`${prefix}:if=`);
    expect(markup).toContain(`${prefix}:else`);
    expect(markup).toContain(`${prefix}:for=`);
    expect(markup).toContain(`${prefix}:for-item="item"`);
    expect(markup).toContain(`${prefix}:key="id"`);
    expect(markup).toContain(`${event}="handleClickButton0"`);
    expect(markup).toContain(`data-cc0="{{ item.id }}"`);
    expect(markup).toContain(`<status-chip label="{{ title }}" />`);
    expect(markup).not.toMatch(/<(?:div|section|h2|ul|li|strong|em)(?:\s|>)/);

    const config = JSON.parse(files.json as string) as { component: boolean; usingComponents: Record<string, string> };
    expect(config).toEqual({ component: true, usingComponents: { "status-chip": "/components/StatusChip/index" } });
  });

  it("emits structurally balanced markup and syntactically valid JavaScript", () => {
    const files = emitPlatformMiniApp(component, platform).files;
    expectBalancedTemplate(files[template] as string);
    expect(syntaxErrors(files.js as string)).toEqual([]);
    expect(() => JSON.parse(files.json as string)).not.toThrow();
  });

  it("preserves loop-local event data and pre-update closure reads", () => {
    const js = emitPlatformMiniApp(component, platform).files.js as string;
    expect(js).toContain("const ccLocal0 = event.currentTarget.dataset.cc0;");
    expect(js).toContain("const count$0 = this.data.count;");
    expect(js).toContain("this.setData({ count: count$0 + ccLocal0 });");
    if (platform === "alipay") {
      expect(js).toContain("props: {");
      expect(js).toContain('if (typeof this.props.onDone === "function") { this.props.onDone(ccLocal0); }');
      expect(js).not.toContain("triggerEvent(");
    } else {
      expect(js).toContain("properties: {");
      expect(js).toContain('this.triggerEvent("done", { value: ccLocal0 });');
    }
  });
});
describe("mini-app emitter safety and real local parser evidence", () => {
  it("escapes literal markup rather than creating injected target nodes", () => {
    const component = parseReactComponent(
      `function Safe() { return (<div>{"</view><script>not-code</script>"}</div>); }`,
      "Safe.tsx",
    );
    for (const testCase of CASES) {
      const emission = emitPlatformMiniApp(component, testCase.platform);
      const markup = emission.files[testCase.template] as string;
      expect(markup).toContain("&lt;/view&gt;&lt;script&gt;not-code&lt;/script&gt;");
      expect(markup).not.toContain("<script>");
    }

    const unsafeStaticLiterals = [
      parseReactComponent(
        `function UnsafeText() { return (<div>{"{{ label }}"}</div>); }`,
        "UnsafeText.tsx",
      ),
      parseReactComponent(
        `function UnsafeAttribute() { return (<a href="{{ route }}">open</a>); }`,
        "UnsafeAttribute.tsx",
      ),
      parseReactComponent(
        `function UnsafeClass() { return (<div className="{{ cssClass }}">open</div>); }`,
        "UnsafeClass.tsx",
      ),
    ];
    for (const unsafe of unsafeStaticLiterals) {
      for (const testCase of CASES) {
        expect(() => emitPlatformMiniApp(unsafe, testCase.platform)).toThrow(
          /MINIAPP_UNSAFE_STATIC_TEMPLATE_DELIMITER/u,
        );
      }
    }

    const collidingChildren = parseReactComponent(
      `function Collision({ label }: { label: string }) { return (<div><StatusChip label={label} /><StatusCHip label={label} /></div>); }`,
      "Collision.tsx",
    );
    expect(() => emitPlatformMiniApp(collidingChildren, "wechat")).toThrow(
      /MINIAPP_TARGET_NAME_COLLISION/u,
    );

    const collidingProps = parseReactComponent(
      `function Collision({ label }: { label: string }) { return (<StatusChip fooBar={label} fooBAR={label} />); }`,
      "Collision.tsx",
    );
    expect(() => emitPlatformMiniApp(collidingProps, "wechat")).toThrow(
      /MINIAPP_TARGET_NAME_COLLISION/u,
    );
  });

  it("feeds the WeChat output through the installed real WXML parser", () => {
    const component = parseReactComponent(SOURCE, "Dashboard.tsx");
    const files = emitPlatformMiniApp(component, "wechat").files;
    expect(validateSyntax("miniprogram", files)).toEqual({ status: "PASSED", diagnostics: [] });
    expect(() => emitPlatformMiniApp(component, "baidu" as MiniAppPlatform)).toThrow(
      /MINIAPP_UNSUPPORTED_PLATFORM/u,
    );
  });
});
