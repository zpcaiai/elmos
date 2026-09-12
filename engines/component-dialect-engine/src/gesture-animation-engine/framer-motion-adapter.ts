/**
 * @file framer-motion-adapter.ts
 * @description Code Generator for React Framer Motion Components.
 * Compiles ComponentMotionIR into typed Framer Motion JSX code with:
 * - Spring physics transitions (stiffness, damping, mass)
 * - Cubic-bezier and tween easing sequences
 * - Gesture bindings (drag, pan, hover, tap, exit)
 * - AnimatePresence exit animations
 * - Full TypeScript props interface
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform).
 */

import {
  ComponentMotionIR,
  MotionStateVariantIR,
  GestureAnimationEmitResult,
  SpringPhysicsConfigIR,
  KeyframeAnimationConfigIR,
} from './gesture-ir-types';

export class FramerMotionAdapter {
  /**
   * Emit React Framer Motion component code.
   */
  public emitComponent(
    componentName: string,
    motionIR: ComponentMotionIR
  ): GestureAnimationEmitResult {
    const warnings: string[] = [];

    // Check for exit variant without AnimatePresence notice
    const hasExit = Boolean(motionIR.exitVariant);

    const variantsCode = this.generateVariantsObject(motionIR.variants, warnings);
    const componentCode = this.generateComponentBody(
      componentName,
      motionIR,
      hasExit
    );

    return {
      targetFramework: 'framer-motion',
      componentCode,
      helperCode: variantsCode,
      warnings,
    };
  }

  /**
   * Generates Framer Motion Variants dictionary.
   */
  private generateVariantsObject(
    variants: Record<string, MotionStateVariantIR>,
    warnings: string[]
  ): string {
    const entries = Object.entries(variants);
    if (entries.length === 0) {
      return `export const motionVariants = {};\n`;
    }

    const lines: string[] = [`export const motionVariants: Record<string, any> = {`];

    for (const [key, variant] of entries) {
      lines.push(`  ${JSON.stringify(key)}: {`);

      // Properties
      for (const [prop, val] of Object.entries(variant.properties)) {
        if (val !== undefined) {
          lines.push(`    ${prop}: ${typeof val === 'string' ? JSON.stringify(val) : val},`);
        }
      }

      // Transition
      if (variant.transition) {
        lines.push(`    transition: {`);
        if (variant.transition.type === 'spring' && variant.transition.spring) {
          const sp: SpringPhysicsConfigIR = variant.transition.spring;
          lines.push(`      type: 'spring',`);
          lines.push(`      stiffness: ${sp.stiffness},`);
          lines.push(`      damping: ${sp.damping},`);
          if (sp.mass !== undefined) lines.push(`      mass: ${sp.mass},`);
          if (sp.velocity !== undefined) lines.push(`      velocity: ${sp.velocity},`);
          if (sp.restSpeed !== undefined) lines.push(`      restSpeed: ${sp.restSpeed},`);
          if (sp.restDelta !== undefined) lines.push(`      restDelta: ${sp.restDelta},`);
        } else if (variant.transition.type === 'tween' && variant.transition.tween) {
          const tw: KeyframeAnimationConfigIR = variant.transition.tween;
          lines.push(`      type: 'tween',`);
          lines.push(`      duration: ${tw.durationMs / 1000},`);
          lines.push(`      ease: ${JSON.stringify(tw.easing)},`);
          if (tw.delayMs) lines.push(`      delay: ${tw.delayMs / 1000},`);
          if (tw.repeat) {
            lines.push(`      repeat: ${tw.repeat === 'infinite' ? 'Infinity' : tw.repeat},`);
            if (tw.repeatType) lines.push(`      repeatType: ${JSON.stringify(tw.repeatType)},`);
          }
        }
        lines.push(`    },`);
      }

      lines.push(`  },`);
    }

    lines.push(`};`);
    return lines.join('\n');
  }

  /**
   * Generates the React functional component with motion.div and gesture attributes.
   */
  private generateComponentBody(
    componentName: string,
    motionIR: ComponentMotionIR,
    hasExit: boolean
  ): string {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated Framer Motion Animated Component: ${componentName}`,
      ` */`,
      `import React from 'react';`,
      hasExit
        ? `import { motion, AnimatePresence, PanInfo } from 'framer-motion';`
        : `import { motion, PanInfo } from 'framer-motion';`,
      '',
      this.generateVariantsObject(motionIR.variants, []),
      '',
      `export interface ${componentName}Props {`,
      `  children?: React.ReactNode;`,
      `  className?: string;`,
      `  style?: React.CSSProperties;`,
      `  isVisible?: boolean;`,
      `  onPanStart?: (event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => void;`,
      `  onPanEnd?: (event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => void;`,
      `  onTap?: () => void;`,
      `}`,
      '',
      `export const ${componentName}: React.FC<${componentName}Props> = ({`,
      `  children,`,
      `  className = '',`,
      `  style,`,
      `  isVisible = true,`,
      `  onPanStart,`,
      `  onPanEnd,`,
      `  onTap,`,
      `}) => {`,
    ];

    const motionAttrs: string[] = [
      `className={className}`,
      `style={style}`,
      `variants={motionVariants}`,
    ];

    if (motionIR.initialVariant) {
      motionAttrs.push(`initial=${JSON.stringify(motionIR.initialVariant)}`);
    }
    if (motionIR.animateVariant) {
      motionAttrs.push(`animate=${JSON.stringify(motionIR.animateVariant)}`);
    }
    if (motionIR.exitVariant) {
      motionAttrs.push(`exit=${JSON.stringify(motionIR.exitVariant)}`);
    }
    if (motionIR.whileHoverVariant) {
      motionAttrs.push(`whileHover=${JSON.stringify(motionIR.whileHoverVariant)}`);
    }
    if (motionIR.whileTapVariant) {
      motionAttrs.push(`whileTap=${JSON.stringify(motionIR.whileTapVariant)}`);
    }

    // Drag attributes
    if (motionIR.drag !== undefined) {
      if (typeof motionIR.drag === 'boolean') {
        motionAttrs.push(`drag={${motionIR.drag}}`);
      } else {
        motionAttrs.push(`drag=${JSON.stringify(motionIR.drag)}`);
      }

      if (motionIR.dragConstraints) {
        motionAttrs.push(`dragConstraints={${JSON.stringify(motionIR.dragConstraints)}}`);
      }
      if (motionIR.dragElastic !== undefined) {
        motionAttrs.push(`dragElastic={${JSON.stringify(motionIR.dragElastic)}}`);
      }
    }

    // Gesture event handlers
    const hasPan = motionIR.gestures.some((g) => g.gestureType === 'pan' || g.gestureType === 'swipe');
    if (hasPan) {
      motionAttrs.push(`onPanStart={onPanStart}`);
      motionAttrs.push(`onPanEnd={onPanEnd}`);
    }

    const hasTap = motionIR.gestures.some((g) => g.gestureType === 'tap');
    if (hasTap) {
      motionAttrs.push(`onTap={onTap}`);
    }

    if (hasExit) {
      lines.push(`  return (`);
      lines.push(`    <AnimatePresence>`);
      lines.push(`      {isVisible && (`);
      lines.push(`        <motion.div`);
      for (const attr of motionAttrs) {
        lines.push(`          ${attr}`);
      }
      lines.push(`        >`);
      lines.push(`          {children}`);
      lines.push(`        </motion.div>`);
      lines.push(`      )}`);
      lines.push(`    </AnimatePresence>`);
      lines.push(`  );`);
    } else {
      lines.push(`  return (`);
      lines.push(`    <motion.div`);
      for (const attr of motionAttrs) {
        lines.push(`      ${attr}`);
      }
      lines.push(`    >`);
      lines.push(`      {children}`);
      lines.push(`    </motion.div>`);
      lines.push(`  );`);
    }

    lines.push(`};`);
    return lines.join('\n');
  }
}
