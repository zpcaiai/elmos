import { FullSyntaxComponentIR, TargetFramework } from "../types";

export class ContainerApiTransformer {
  private static readonly MINIAPP_API_MAP: Record<string, string> = {
    "window.location.href": "wx.navigateTo",
    "window.location": "wx.navigateTo",
    "window.alert": "wx.showModal",
    "alert": "wx.showToast",
    "localStorage.getItem": "wx.getStorageSync",
    "localStorage.setItem": "wx.setStorageSync",
    "localStorage.removeItem": "wx.removeStorageSync",
    "localStorage.clear": "wx.clearStorageSync",
    "sessionStorage.getItem": "wx.getStorageSync",
    "sessionStorage.setItem": "wx.setStorageSync",
    "navigator.clipboard.writeText": "wx.setClipboardData",
    "document.title": "wx.setNavigationBarTitle",
  };

  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    if (target === "miniapp") {
      for (const method of ir.methods) {
        for (const [webApi, wxApi] of Object.entries(ContainerApiTransformer.MINIAPP_API_MAP)) {
          if (method.bodyCode.includes(webApi)) {
            method.bodyCode = method.bodyCode.replaceAll(webApi, wxApi);
          }
        }
      }
    }
  }
}
