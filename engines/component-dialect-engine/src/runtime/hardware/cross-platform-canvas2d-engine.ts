/**
 * @file cross-platform-canvas2d-engine.ts
 * @description High-Performance Canvas 2D Cross-Platform Engine.
 * Normalizes modern WeChat type="2d" Canvas with HTML5 Canvas 2D,
 * handles Retina/High-DPI devicePixelRatio compensation, and unifies touch/mouse coordinates.
 */

export interface CanvasDimensions {
  width: number;
  height: number;
  dpr: number;
}

export class CrossPlatformCanvas2dEngine {
  private canvasNode: any = null;
  private ctx: CanvasRenderingContext2D | any = null;
  private dpr: number = 1;
  private width: number = 300;
  private height: number = 150;

  /**
   * Initializes Canvas 2D node for WeChat MiniApp or Web HTML5
   */
  public async init(selectorOrId: string, pageInstance?: any): Promise<any> {
    // 1. WeChat MiniApp type="2d" initialization
    if (typeof wx !== 'undefined' && wx.createSelectorQuery) {
      const query = pageInstance ? pageInstance.createSelectorQuery() : wx.createSelectorQuery();
      return new Promise((resolve, reject) => {
        query
          .select(selectorOrId)
          .fields({ node: true, size: true })
          .exec((res: any[]) => {
            const first = res && res[0];
            if (!first || !first.node) {
              reject(new Error(`[Canvas2D] Failed to retrieve canvas node for selector: ${selectorOrId}`));
              return;
            }

            const canvas = first.node;
            const ctx = canvas.getContext('2d');
            const sys = wx.getSystemInfoSync ? wx.getSystemInfoSync() : { pixelRatio: 2 };
            const dpr = sys.pixelRatio || 2;

            canvas.width = first.width * dpr;
            canvas.height = first.height * dpr;
            ctx.scale(dpr, dpr);

            this.canvasNode = canvas;
            this.ctx = ctx;
            this.dpr = dpr;
            this.width = first.width;
            this.height = first.height;

            resolve(ctx);
          });
      });
    }

    // 2. Web DOM Canvas fallback
    if (typeof document !== 'undefined') {
      const el = document.querySelector(selectorOrId) as HTMLCanvasElement;
      if (el && el.getContext) {
        const ctx = el.getContext('2d');
        const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
        const rect = el.getBoundingClientRect();

        el.width = rect.width * dpr;
        el.height = rect.height * dpr;
        if (ctx) ctx.scale(dpr, dpr);

        this.canvasNode = el;
        this.ctx = ctx;
        this.dpr = dpr;
        this.width = rect.width;
        this.height = rect.height;
        return ctx;
      }
    }

    // 3. Headless mock canvas for testing
    const mockCtx = this.createMock2dContext();
    this.ctx = mockCtx;
    return mockCtx;
  }

  public getContext(): any {
    return this.ctx;
  }

  public getDimensions(): CanvasDimensions {
    return {
      width: this.width,
      height: this.height,
      dpr: this.dpr,
    };
  }

  /**
   * Clears the entire canvas
   */
  public clear(): void {
    if (this.ctx) {
      this.ctx.clearRect(0, 0, this.width, this.height);
    }
  }

  /**
   * Normalizes touch or mouse coordinates to logical canvas pixels
   */
  public normalizeEventCoordinates(event: any): { x: number; y: number } {
    if (event.touches && event.touches.length > 0) {
      const t = event.touches[0];
      return { x: t.x ?? t.clientX ?? 0, y: t.y ?? t.clientY ?? 0 };
    }
    return { x: event.offsetX ?? event.clientX ?? 0, y: event.offsetY ?? event.clientY ?? 0 };
  }

  /**
   * Export to image (wx.canvasToTempFilePath or HTML5 toDataURL)
   */
  public async exportToImage(): Promise<string> {
    if (typeof wx !== 'undefined' && wx.canvasToTempFilePath && this.canvasNode) {
      return new Promise((resolve, reject) => {
        wx.canvasToTempFilePath({
          canvas: this.canvasNode,
          success: (res: any) => resolve(res.tempFilePath),
          fail: (err: any) => reject(new Error(err.errMsg || 'canvasToTempFilePath failed')),
        });
      });
    }

    if (this.canvasNode && typeof this.canvasNode.toDataURL === 'function') {
      return this.canvasNode.toDataURL('image/png');
    }

    return 'data:image/png;base64,mock_canvas_export';
  }

  private createMock2dContext(): any {
    const ops: string[] = [];
    return {
      scale: (x: number, y: number) => ops.push(`scale(${x},${y})`),
      clearRect: (x: number, y: number, w: number, h: number) => ops.push(`clearRect(${x},${y},${w},${h})`),
      fillRect: (x: number, y: number, w: number, h: number) => ops.push(`fillRect(${x},${y},${w},${h})`),
      beginPath: () => ops.push('beginPath'),
      moveTo: (x: number, y: number) => ops.push(`moveTo(${x},${y})`),
      lineTo: (x: number, y: number) => ops.push(`lineTo(${x},${y})`),
      stroke: () => ops.push('stroke'),
      fill: () => ops.push('fill'),
      set fillStyle(val: string) {
        ops.push(`fillStyle=${val}`);
      },
      set strokeStyle(val: string) {
        ops.push(`strokeStyle=${val}`);
      },
      _ops: ops,
    };
  }
}
