import { FullSyntaxComponentIR, FullSyntaxEffect, TargetFramework } from "../types";

export class EffectLifecycleTransformer {
  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    const transformedEffects: FullSyntaxEffect[] = [];

    for (const eff of ir.effects) {
      const effectCopy = { ...eff };

      if (target === "miniapp") {
        // Adapt body code for MiniProgram: replace setState/this.state with this.setData
        effectCopy.bodyCode = this.adaptForMiniProgram(effectCopy.bodyCode);
      } else if (target === "vue3") {
        effectCopy.bodyCode = this.adaptForVue3(effectCopy.bodyCode);
      } else if (target === "react") {
        effectCopy.bodyCode = this.adaptForReact(effectCopy.bodyCode);
      }

      transformedEffects.push(effectCopy);
    }

    ir.effects = transformedEffects;
  }

  private adaptForMiniProgram(code: string): string {
    return code
      .replace(/set([A-Z][a-zA-Z0-9_]*)\(([^)]+)\)/g, (_m, p1, p2) => {
        const stateKey = p1.charAt(0).toLowerCase() + p1.slice(1);
        return `this.setData({ ${stateKey}: ${p2} })`;
      })
      .replace(/localStorage\.getItem\(([^)]+)\)/g, "wx.getStorageSync($1)")
      .replace(/localStorage\.setItem\(([^,]+),\s*([^)]+)\)/g, "wx.setStorageSync($1, $2)")
      .replace(/sessionStorage\.getItem\(([^)]+)\)/g, "wx.getStorageSync($1)")
      .replace(/sessionStorage\.setItem\(([^,]+),\s*([^)]+)\)/g, "wx.setStorageSync($1, $2)")
      .replace(/window\.location\.href\s*=\s*([^;]+)/g, "wx.navigateTo({ url: $1 })")
      .replace(/window\.alert\(([^)]+)\)/g, "wx.showModal({ title: 'Alert', content: String($1) })");
  }

  private adaptForVue3(code: string): string {
    return code
      .replace(/set([A-Z][a-zA-Z0-9_]*)\(([^)]+)\)/g, (_m, p1, p2) => {
        const stateKey = p1.charAt(0).toLowerCase() + p1.slice(1);
        return `${stateKey}.value = ${p2}`;
      })
      .replace(/this\.setData\(\{\s*([a-zA-Z0-9_]+):\s*([^}]+)\}\)/g, "$1.value = $2");
  }

  private adaptForReact(code: string): string {
    return code
      .replace(/this\.setData\(\{\s*([a-zA-Z0-9_]+):\s*([^}]+)\}\)/g, (_m, p1, p2) => {
        const setterName = "set" + p1.charAt(0).toUpperCase() + p1.slice(1);
        return `${setterName}(${p2})`;
      })
      .replace(/([a-zA-Z0-9_]+)\.value\s*=\s*([^;]+)/g, (_m, p1, p2) => {
        const setterName = "set" + p1.charAt(0).toUpperCase() + p1.slice(1);
        return `${setterName}(${p2})`;
      });
  }
}
