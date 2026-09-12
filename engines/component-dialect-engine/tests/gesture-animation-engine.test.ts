/**
 * @file gesture-animation-engine.test.ts
 * @description Comprehensive Test Suite for Gesture and Animation Engine.
 * Validates:
 * 1. Framer Motion code emission with variants and spring physics
 * 2. Tween / cubic-bezier and keyframe repeat configurations
 * 3. AnimatePresence conditional exit animation wrappers
 * 4. WeChat MiniApp WXS zero-latency gesture responder generation
 * 5. WeChat MiniApp wx.createAnimation() programmatic state transitions
 * 6. Touch gesture boundaries, constraints, and warnings
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform) & Execution Integrity Contract.
 */

import {
  FramerMotionAdapter,
  MiniAppAnimationAdapter,
  ComponentMotionIR,
} from '../src/gesture-animation-engine';

describe('Gesture and Animation Engine Suite', () => {
  describe('FramerMotionAdapter', () => {
    const adapter = new FramerMotionAdapter();

    it('should emit standard Framer Motion component with spring physics variants', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'card-motion',
        gestures: [],
        variants: {
          initial: {
            name: 'initial',
            properties: { opacity: 0, y: 50, scale: 0.95 },
          },
          animate: {
            name: 'animate',
            properties: { opacity: 1, y: 0, scale: 1 },
            transition: {
              type: 'spring',
              spring: {
                stiffness: 300,
                damping: 25,
                mass: 1.2,
                restDelta: 0.001,
              },
            },
          },
        },
        initialVariant: 'initial',
        animateVariant: 'animate',
      };

      const result = adapter.emitComponent('AnimatedCard', motionIR);

      expect(result.targetFramework).toBe('framer-motion');
      expect(result.componentCode).toContain('export const AnimatedCard: React.FC<AnimatedCardProps>');
      expect(result.componentCode).toContain('initial="initial"');
      expect(result.componentCode).toContain('animate="animate"');
      expect(result.helperCode).toContain('stiffness: 300');
      expect(result.helperCode).toContain('damping: 25');
      expect(result.helperCode).toContain('mass: 1.2');
      expect(result.warnings.length).toBe(0);
    });

    it('should wrap in AnimatePresence when exit variant is provided', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'modal-motion',
        gestures: [],
        variants: {
          initial: {
            name: 'initial',
            properties: { opacity: 0, scale: 0.8 },
          },
          animate: {
            name: 'animate',
            properties: { opacity: 1, scale: 1 },
          },
          exit: {
            name: 'exit',
            properties: { opacity: 0, scale: 0.8 },
            transition: {
              type: 'tween',
              tween: {
                durationMs: 200,
                easing: 'easeOut',
              },
            },
          },
        },
        initialVariant: 'initial',
        animateVariant: 'animate',
        exitVariant: 'exit',
      };

      const result = adapter.emitComponent('AnimatedModal', motionIR);

      expect(result.componentCode).toContain('<AnimatePresence>');
      expect(result.componentCode).toContain('isVisible &&');
      expect(result.componentCode).toContain('exit="exit"');
      expect(result.helperCode).toContain('duration: 0.2');
    });

    it('should configure drag gestures, constraints, and elastic boundaries', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'draggable-slider',
        gestures: [
          {
            id: 'pan-1',
            gestureType: 'pan',
            enabled: true,
            config: { direction: 'horizontal', threshold: 10 },
          },
        ],
        variants: {
          idle: { name: 'idle', properties: { x: 0 } },
        },
        drag: 'x',
        dragConstraints: { left: -300, right: 0 },
        dragElastic: 0.2,
      };

      const result = adapter.emitComponent('DraggableSlider', motionIR);

      expect(result.componentCode).toContain('drag="x"');
      expect(result.componentCode).toContain('dragConstraints={{"left":-300,"right":0}}');
      expect(result.componentCode).toContain('dragElastic={0.2}');
      expect(result.componentCode).toContain('onPanStart={onPanStart}');
      expect(result.componentCode).toContain('onPanEnd={onPanEnd}');
    });

    it('should handle infinite repeat tween animations', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'pulse-badge',
        gestures: [],
        variants: {
          pulse: {
            name: 'pulse',
            properties: { scale: 1.1, opacity: 0.7 },
            transition: {
              type: 'tween',
              tween: {
                durationMs: 1000,
                easing: 'easeInOut',
                repeat: 'infinite',
                repeatType: 'reverse',
              },
            },
          },
        },
        animateVariant: 'pulse',
      };

      const result = adapter.emitComponent('PulseBadge', motionIR);

      expect(result.helperCode).toContain('repeat: Infinity');
      expect(result.helperCode).toContain("repeatType: \"reverse\"");
    });
  });

  describe('MiniAppAnimationAdapter', () => {
    const adapter = new MiniAppAnimationAdapter();

    it('should emit WXS gesture responder for 60FPS fluid touch dragging', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'sheet-drag',
        gestures: [
          {
            id: 'g-pan',
            gestureType: 'pan',
            enabled: true,
            config: { direction: 'vertical', threshold: 8 },
          },
        ],
        variants: {
          open: { name: 'open', properties: { y: 0 } },
          closed: { name: 'closed', properties: { y: 400 } },
        },
        drag: 'y',
        dragConstraints: { top: 0, bottom: 400 },
      };

      const result = adapter.emitComponent(motionIR, { componentName: 'BottomSheet' });

      expect(result.targetFramework).toBe('miniapp-wxs-animation');
      expect(result.wxsCode).toBeDefined();
      expect(result.wxsCode).toContain('function touchStart(event, ownerInstance)');
      expect(result.wxsCode).toContain('function touchMove(event, ownerInstance)');
      expect(result.wxsCode).toContain('function touchEnd(event, ownerInstance)');
      expect(result.wxsCode).toContain('translate3d');
      expect(result.wxsCode).toContain('callMethod');
      expect(result.componentCode).toContain('<wxs module="gesture" src="./BottomSheet.wxs"></wxs>');
      expect(result.componentCode).toContain('catchtouchstart="{{gesture.touchStart}}"');
    });

    it('should emit wx.createAnimation programmatic transitions in JS component', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'fade-box',
        gestures: [],
        variants: {
          hidden: { name: 'hidden', properties: { opacity: 0, scale: 0.5 } },
          visible: { name: 'visible', properties: { opacity: 1, scale: 1, rotate: 360 } },
        },
        initialVariant: 'hidden',
      };

      const result = adapter.emitComponent(motionIR, { componentName: 'FadeBox' });

      expect(result.componentCode).toContain('wx.createAnimation');
      expect(result.componentCode).toContain('anim.opacity(0)');
      expect(result.componentCode).toContain('anim.opacity(1)');
      expect(result.componentCode).toContain('anim.scale(1)');
      expect(result.componentCode).toContain('anim.rotate(360)');
      expect(result.componentCode).toContain('animationData: anim.export()');
    });

    it('should warn when drag is configured with WXS disabled', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'pan-box',
        gestures: [
          {
            id: 'g-pan',
            gestureType: 'pan',
            enabled: true,
            config: { direction: 'all' },
          },
        ],
        variants: {},
        drag: true,
      };

      const result = adapter.emitComponent(motionIR, { enableWxsGestures: false });
      expect(result.warnings.some((w) => w.includes('WXS responder'))).toBe(true);
      expect(result.wxsCode).toBeUndefined();
    });

    it('should generate hardware-accelerated WXSS rules', () => {
      const motionIR: ComponentMotionIR = {
        componentId: 'simple-box',
        gestures: [],
        variants: {},
      };

      const result = adapter.emitComponent(motionIR);
      expect(result.styleCode).toContain('will-change: transform, opacity');
      expect(result.styleCode).toContain('transform: translate3d(0, 0, 0)');
    });
  });
});
