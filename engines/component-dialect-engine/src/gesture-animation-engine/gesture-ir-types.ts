/**
 * @file gesture-ir-types.ts
 * @description Universal Gesture and Motion Animation IR Types.
 * Models cross-framework touch/pointer gestures and physics-based spring / keyframe animations.
 * Supports:
 * - Touch gestures: Pan, Pinch, Swipe, Rotate, LongPress, Tap, DoubleTap
 * - Animation models: Spring dynamics (stiffness, damping, mass), Bezier curves, Keyframe sequences
 * - Gesture recognition state machines: Possible -> Began -> Changed -> Ended / Cancelled
 * - Cross-framework targets: React (Framer Motion), Vue (Motion One), MiniApp (wx.createAnimation & WXS), ArkUI
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform) & Skill 1203 (b32-mobile-crossplatform).
 */

export type GestureType =
  | 'pan'
  | 'pinch'
  | 'swipe'
  | 'rotate'
  | 'longPress'
  | 'tap'
  | 'doubleTap';

export type GestureState =
  | 'possible'
  | 'began'
  | 'changed'
  | 'ended'
  | 'cancelled'
  | 'failed';

export type GestureDirection = 'up' | 'down' | 'left' | 'right' | 'horizontal' | 'vertical' | 'all';

export interface PanGestureConfigIR {
  direction?: GestureDirection;
  threshold?: number; // Minimum movement in px before gesture begins
  maxPointers?: number;
  lockDirection?: boolean; // Lock to primary axis once movement begins
}

export interface PinchGestureConfigIR {
  minScale?: number;
  maxScale?: number;
  threshold?: number;
}

export interface SwipeGestureConfigIR {
  direction: GestureDirection;
  minDistance?: number;
  velocityThreshold?: number; // px / ms
}

export interface LongPressGestureConfigIR {
  minDurationMs?: number; // Time in ms before long press fires (default 500ms)
  maxMoveTolerance?: number; // Max px movement allowed during press
}

export interface TapGestureConfigIR {
  numberOfTaps?: number; // 1 for tap, 2 for double tap
  maxDelayBetweenTapsMs?: number;
}

export interface UniversalGestureBindingIR {
  id: string;
  gestureType: GestureType;
  enabled: boolean;
  config:
    | PanGestureConfigIR
    | PinchGestureConfigIR
    | SwipeGestureConfigIR
    | LongPressGestureConfigIR
    | TapGestureConfigIR;
  preventDefault?: boolean;
  stopPropagation?: boolean;
}

export interface SpringPhysicsConfigIR {
  stiffness: number; // Spring tension (e.g. 100 - 500)
  damping: number; // Friction / resistance (e.g. 10 - 40)
  mass?: number; // Inertia (default 1.0)
  velocity?: number; // Initial velocity
  restSpeed?: number; // Speed below which spring is considered at rest
  restDelta?: number; // Distance below which spring is considered at rest
}

export type EasingCurve =
  | 'linear'
  | 'easeIn'
  | 'easeOut'
  | 'easeInOut'
  | 'circIn'
  | 'circOut'
  | 'circInOut'
  | 'backIn'
  | 'backOut'
  | 'backInOut'
  | [number, number, number, number]; // Cubic bezier points [x1, y1, x2, y2]

export interface KeyframeAnimationConfigIR {
  durationMs: number;
  easing: EasingCurve;
  delayMs?: number;
  repeat?: number | 'infinite';
  repeatType?: 'loop' | 'reverse' | 'mirror';
}

export interface MotionTransformPropertiesIR {
  x?: number | string; // px or %
  y?: number | string;
  z?: number | string;
  scale?: number;
  scaleX?: number;
  scaleY?: number;
  rotate?: number | string; // deg or rad
  rotateX?: number | string;
  rotateY?: number | string;
  rotateZ?: number | string;
  opacity?: number; // 0 to 1
  backgroundColor?: string;
  borderRadius?: number | string;
  boxShadow?: string;
  width?: number | string;
  height?: number | string;
}

export interface MotionStateVariantIR {
  name: string; // e.g. 'initial', 'animate', 'exit', 'hover', 'tap'
  properties: MotionTransformPropertiesIR;
  transition?: {
    type: 'spring' | 'tween' | 'keyframes';
    spring?: SpringPhysicsConfigIR;
    tween?: KeyframeAnimationConfigIR;
  };
}

export interface ComponentMotionIR {
  componentId: string;
  gestures: UniversalGestureBindingIR[];
  variants: Record<string, MotionStateVariantIR>;
  initialVariant?: string;
  animateVariant?: string;
  exitVariant?: string;
  whileHoverVariant?: string;
  whileTapVariant?: string;
  drag?: boolean | 'x' | 'y';
  dragConstraints?: {
    top?: number;
    bottom?: number;
    left?: number;
    right?: number;
  };
  dragElastic?: number | boolean;
}

export type GestureAnimationFrameworkId =
  | 'framer-motion'
  | 'motion-one'
  | 'miniapp-wxs-animation'
  | 'arkui-motion';

export interface GestureAnimationEmitResult {
  targetFramework: GestureAnimationFrameworkId;
  componentCode: string;
  helperCode?: string;
  styleCode?: string;
  wxsCode?: string; // WeChat MiniApp WXS responder
  warnings: string[];
}
