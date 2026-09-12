/**
 * @file miniapp-animation-adapter.ts
 * @description WeChat MiniApp Gesture Responder and Animation Adapter.
 * Compiles ComponentMotionIR into:
 * 1. Zero-latency WXS (WeiXin Script) Gesture Responder executing directly in View thread
 * 2. wx.createAnimation() programmatic transition sequences for JS thread
 * 3. Hardware-accelerated CSS3 @keyframes and WXSS transitions
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform) & Skill 1203 (b32-mobile-crossplatform).
 */

import {
  ComponentMotionIR,
  GestureAnimationEmitResult,
  PanGestureConfigIR,
  SwipeGestureConfigIR,
} from './gesture-ir-types';

export interface MiniAppAnimationOptions {
  componentName?: string;
  enableWxsGestures?: boolean;
  useRpx?: boolean;
}

export class MiniAppAnimationAdapter {
  /**
   * Emit WeChat MiniApp Gesture & Animation bundle (WXML, WXS, JS/TS, WXSS).
   */
  public emitComponent(
    motionIR: ComponentMotionIR,
    options: MiniAppAnimationOptions = {}
  ): GestureAnimationEmitResult {
    const componentName = options.componentName || 'MiniAppMotionView';
    const enableWxs = options.enableWxsGestures ?? true;
    const warnings: string[] = [];

    // Check for drag or pan gestures
    const panGesture = motionIR.gestures.find(
      (g) => g.gestureType === 'pan' || g.gestureType === 'swipe'
    );

    const hasDrag = motionIR.drag !== undefined || Boolean(panGesture);

    if (hasDrag && !enableWxs) {
      warnings.push(
        `Drag/Pan gesture configured without WXS responder. High-frequency touch events over the JS-bridge may cause stuttering at 60FPS.`
      );
    }

    const useWxs = hasDrag && enableWxs;
    const wxsCode = useWxs ? this.generateWxsGestureResponder(motionIR) : '';
    const wxmlCode = this.generateWxml(componentName, useWxs);
    const jsCode = this.generateJsComponent(componentName, motionIR);
    const wxssCode = this.generateWxss(motionIR, options.useRpx);

    const fullComponentCode = [
      `// ==========================================`,
      `// [${componentName}.wxml]`,
      `// ==========================================`,
      wxmlCode,
      ``,
      `// ==========================================`,
      `// [${componentName}.ts / ${componentName}.js]`,
      `// ==========================================`,
      jsCode,
      ``,
      `// ==========================================`,
      `// [${componentName}.wxss]`,
      `// ==========================================`,
      wxssCode,
    ].join('\n');

    return {
      targetFramework: 'miniapp-wxs-animation',
      componentCode: fullComponentCode,
      helperCode: jsCode,
      styleCode: wxssCode,
      wxsCode: wxsCode || undefined,
      warnings,
    };
  }

  /**
   * Generates WXS (WeiXin Script) Gesture Responder.
   * Runs directly inside the WebView render process with ZERO bridge latency.
   */
  public generateWxsGestureResponder(motionIR: ComponentMotionIR): string {
    const dragAxis = motionIR.drag === 'x' ? 'x' : motionIR.drag === 'y' ? 'y' : 'all';
    const pan = motionIR.gestures.find((g) => g.gestureType === 'pan')?.config as PanGestureConfigIR | undefined;
    const threshold = pan?.threshold || 5;

    const minX = motionIR.dragConstraints?.left ?? -9999;
    const maxX = motionIR.dragConstraints?.right ?? 9999;
    const minY = motionIR.dragConstraints?.top ?? -9999;
    const maxY = motionIR.dragConstraints?.bottom ?? 9999;

    return [
      `/**`,
      ` * Auto-generated WeChat MiniApp WXS Gesture Responder`,
      ` * Executes on the WebView rendering thread for 60FPS zero-latency dragging`,
      ` */`,
      `var startX = 0;`,
      `var startY = 0;`,
      `var currentX = 0;`,
      `var currentY = 0;`,
      `var isDragging = false;`,
      `var threshold = ${threshold};`,
      `var minX = ${minX};`,
      `var maxX = ${maxX};`,
      `var minY = ${minY};`,
      `var maxY = ${maxY};`,
      `var dragAxis = ${JSON.stringify(dragAxis)};`,
      ``,
      `function touchStart(event, ownerInstance) {`,
      `  var touch = event.touches[0] || event.changedTouches[0];`,
      `  startX = touch.clientX;`,
      `  startY = touch.clientY;`,
      `  isDragging = false;`,
      `}`,
      ``,
      `function touchMove(event, ownerInstance) {`,
      `  var touch = event.touches[0] || event.changedTouches[0];`,
      `  var dx = touch.clientX - startX;`,
      `  var dy = touch.clientY - startY;`,
      ``,
      `  if (!isDragging) {`,
      `    if (Math.abs(dx) > threshold || Math.abs(dy) > threshold) {`,
      `      isDragging = true;`,
      `      ownerInstance.callMethod('onWxsDragStart', { dx: dx, dy: dy });`,
      `    } else {`,
      `      return true;`,
      `    }`,
      `  }`,
      ``,
      `  var nextX = currentX;`,
      `  var nextY = currentY;`,
      ``,
      `  if (dragAxis === 'x' || dragAxis === 'all') {`,
      `    nextX = Math.max(minX, Math.min(maxX, currentX + dx));`,
      `  }`,
      `  if (dragAxis === 'y' || dragAxis === 'all') {`,
      `    nextY = Math.max(minY, Math.min(maxY, currentY + dy));`,
      `  }`,
      ``,
      `  var target = ownerInstance.selectComponent('.motion-target');`,
      `  if (target) {`,
      `    target.setStyle({`,
      `      transform: 'translate3d(' + nextX + 'px, ' + nextY + 'px, 0)',`,
      `      'transition-duration': '0s',`,
      `    });`,
      `  }`,
      `  return false;`,
      `}`,
      ``,
      `function touchEnd(event, ownerInstance) {`,
      `  if (!isDragging) return true;`,
      `  isDragging = false;`,
      ``,
      `  var touch = event.changedTouches[0];`,
      `  var dx = touch.clientX - startX;`,
      `  var dy = touch.clientY - startY;`,
      ``,
      `  if (dragAxis === 'x' || dragAxis === 'all') {`,
      `    currentX = Math.max(minX, Math.min(maxX, currentX + dx));`,
      `  }`,
      `  if (dragAxis === 'y' || dragAxis === 'all') {`,
      `    currentY = Math.max(minY, Math.min(maxY, currentY + dy));`,
      `  }`,
      ``,
      `  var target = ownerInstance.selectComponent('.motion-target');`,
      `  if (target) {`,
      `    target.setStyle({`,
      `      transform: 'translate3d(' + currentX + 'px, ' + currentY + 'px, 0)',`,
      `      'transition-duration': '0.25s',`,
      `    });`,
      `  }`,
      ``,
      `  ownerInstance.callMethod('onWxsDragEnd', {`,
      `    x: currentX,`,
      `    y: currentY,`,
      `    dx: dx,`,
      `    dy: dy,`,
      `  });`,
      `  return false;`,
      `}`,
      ``,
      `function resetPosition(ownerInstance) {`,
      `  currentX = 0;`,
      `  currentY = 0;`,
      `  var target = ownerInstance.selectComponent('.motion-target');`,
      `  if (target) {`,
      `    target.setStyle({`,
      `      transform: 'translate3d(0, 0, 0)',`,
      `      'transition-duration': '0.3s',`,
      `    });`,
      `  }`,
      `}`,
      ``,
      `module.exports = {`,
      `  touchStart: touchStart,`,
      `  touchMove: touchMove,`,
      `  touchEnd: touchEnd,`,
      `  resetPosition: resetPosition,`,
      `};`,
    ].join('\n');
  }

  /**
   * Generates WXML with WXS module injection and event handlers.
   */
  private generateWxml(componentName: string, hasDrag: boolean): string {
    const lines: string[] = [
      `<!-- Auto-generated WeChat MiniApp Animated Motion View WXML -->`,
    ];

    if (hasDrag) {
      lines.push(`<wxs module="gesture" src="./${componentName}.wxs"></wxs>`);
      lines.push(
        `<view`,
        `  class="motion-wrapper"`,
        `  catchtouchstart="{{gesture.touchStart}}"`,
        `  catchtouchmove="{{gesture.touchMove}}"`,
        `  catchtouchend="{{gesture.touchEnd}}"`,
        `>`,
        `  <view`,
        `    class="motion-target"`,
        `    animation="{{animationData}}"`,
        `  >`,
        `    <slot></slot>`,
        `  </view>`,
        `</view>`
      );
    } else {
      lines.push(
        `<view class="motion-wrapper">`,
        `  <view class="motion-target" animation="{{animationData}}">`,
        `    <slot></slot>`,
        `  </view>`,
        `</view>`
      );
    }

    return lines.join('\n');
  }

  /**
   * Generates JS/TS Component with wx.createAnimation() steps.
   */
  private generateJsComponent(
    componentName: string,
    motionIR: ComponentMotionIR
  ): string {
    const variants = motionIR.variants;
    const variantNames = Object.keys(variants);

    return [
      `/**`,
      ` * Auto-generated WeChat MiniApp Motion Component Controller`,
      ` */`,
      `Component({`,
      `  properties: {`,
      `    currentVariant: {`,
      `      type: String,`,
      `      value: ${JSON.stringify(motionIR.initialVariant || 'initial')},`,
      `      observer: 'onVariantChange',`,
      `    },`,
      `  },`,
      `  data: {`,
      `    animationData: {},`,
      `  },`,
      `  lifetimes: {`,
      `    attached() {`,
      `      this.animator = wx.createAnimation({`,
      `        duration: 300,`,
      `        timingFunction: 'ease-out',`,
      `        transformOrigin: '50% 50% 0',`,
      `      });`,
      `      if (this.properties.currentVariant) {`,
      `        this.applyVariant(this.properties.currentVariant);`,
      `      }`,
      `    },`,
      `  },`,
      `  methods: {`,
      `    onVariantChange(newVariant) {`,
      `      if (newVariant) {`,
      `        this.applyVariant(newVariant);`,
      `      }`,
      `    },`,
      `    applyVariant(variantName) {`,
      `      if (!this.animator) return;`,
      `      const anim = this.animator;`,
      ``,
      this.generateVariantSwitch(variants),
      `      this.setData({ animationData: anim.export() });`,
      `    },`,
      `    onWxsDragStart(detail) {`,
      `      this.triggerEvent('dragStart', detail);`,
      `    },`,
      `    onWxsDragEnd(detail) {`,
      `      this.triggerEvent('dragEnd', detail);`,
      `    },`,
      `  },`,
      `});`,
    ].join('\n');
  }

  /**
   * Generates programmatic switch statement for wx.createAnimation steps.
   */
  private generateVariantSwitch(variants: Record<string, any>): string {
    const lines: string[] = [`      switch (variantName) {`];

    for (const [name, variant] of Object.entries(variants)) {
      lines.push(`        case ${JSON.stringify(name)}: {`);
      const props = variant.properties || {};

      if (props.opacity !== undefined) {
        lines.push(`          anim.opacity(${props.opacity});`);
      }
      if (props.scale !== undefined) {
        lines.push(`          anim.scale(${props.scale});`);
      }
      if (props.rotate !== undefined) {
        const rotVal = typeof props.rotate === 'number' ? props.rotate : parseFloat(props.rotate);
        lines.push(`          anim.rotate(${rotVal || 0});`);
      }
      if (props.x !== undefined || props.y !== undefined) {
        const x = typeof props.x === 'number' ? props.x : 0;
        const y = typeof props.y === 'number' ? props.y : 0;
        lines.push(`          anim.translate3d(${x}, ${y}, 0);`);
      }

      lines.push(`          anim.step();`);
      lines.push(`          break;`);
      lines.push(`        }`);
    }

    lines.push(`        default:`);
    lines.push(`          break;`);
    lines.push(`      }`);

    return lines.join('\n');
  }

  /**
   * Generates WXSS stylesheet.
   */
  private generateWxss(motionIR: ComponentMotionIR, useRpx: boolean = false): string {
    return [
      `/* Auto-generated WeChat MiniApp Motion Styles */`,
      `.motion-wrapper {`,
      `  position: relative;`,
      `  display: inline-block;`,
      `  touch-action: none;`,
      `}`,
      ``,
      `.motion-target {`,
      `  will-change: transform, opacity;`,
      `  backface-visibility: hidden;`,
      `  transform: translate3d(0, 0, 0);`,
      `}`,
    ].join('\n');
  }
}
