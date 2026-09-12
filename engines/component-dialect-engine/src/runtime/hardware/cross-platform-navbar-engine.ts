/**
 * @file cross-platform-navbar-engine.ts
 * @description Enterprise Custom Navigation Bar & SafeArea Layout Engine.
 * Dynamically computes WeChat capsule button bounding metrics (getMenuButtonBoundingClientRect),
 * status bar height, top/bottom safe areas, and provides responsive alignment for custom headers.
 */

export interface CapsuleMetrics {
  width: number;
  height: number;
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface NavigationBarLayout {
  statusBarHeight: number;
  navBarHeight: number;
  totalHeaderHeight: number;
  capsuleMetrics: CapsuleMetrics;
  safeAreaTop: number;
  safeAreaBottom: number;
  titleMaxWidth: number;
}

export class CrossPlatformNavBarEngine {
  private static cachedLayout: NavigationBarLayout | null = null;

  /**
   * Computes precise navigation bar layout dimensions
   */
  public static getLayout(): NavigationBarLayout {
    if (this.cachedLayout) {
      return this.cachedLayout;
    }

    // 1. WeChat MiniApp environment
    if (typeof wx !== 'undefined' && wx.getMenuButtonBoundingClientRect && wx.getSystemInfoSync) {
      try {
        const sys = wx.getSystemInfoSync();
        const capsule = wx.getMenuButtonBoundingClientRect();

        const statusBarHeight = sys.statusBarHeight || 20;
        // Capsule top minus status bar gives gap; navBarHeight = capsule.height + gap * 2
        const gap = capsule.top - statusBarHeight;
        const navBarHeight = capsule.height + gap * 2;
        const totalHeaderHeight = statusBarHeight + navBarHeight;
        const safeAreaTop = sys.safeArea ? sys.safeArea.top : statusBarHeight;
        const safeAreaBottom = sys.safeArea ? sys.screenHeight - sys.safeArea.bottom : 0;
        const titleMaxWidth = capsule.left - 40;

        const layout: NavigationBarLayout = {
          statusBarHeight,
          navBarHeight,
          totalHeaderHeight,
          capsuleMetrics: {
            width: capsule.width,
            height: capsule.height,
            top: capsule.top,
            right: capsule.right,
            bottom: capsule.bottom,
            left: capsule.left,
          },
          safeAreaTop,
          safeAreaBottom,
          titleMaxWidth,
        };

        this.cachedLayout = layout;
        return layout;
      } catch (err) {
        console.warn('[NavBarEngine] Failed to read MiniApp system info, falling back to default:', err);
      }
    }

    // 2. Web or Mobile Web fallback
    const defaultLayout: NavigationBarLayout = {
      statusBarHeight: 44, // standard iOS safe area
      navBarHeight: 44,
      totalHeaderHeight: 88,
      capsuleMetrics: {
        width: 87,
        height: 32,
        top: 50,
        right: 368,
        bottom: 82,
        left: 281,
      },
      safeAreaTop: 44,
      safeAreaBottom: 34,
      titleMaxWidth: 240,
    };

    this.cachedLayout = defaultLayout;
    return defaultLayout;
  }

  /**
   * Generates inline WXSS/CSS style string for custom navigation header container
   */
  public static getHeaderStyleString(): string {
    const layout = this.getLayout();
    return `height: ${layout.totalHeaderHeight}px; padding-top: ${layout.statusBarHeight}px; box-sizing: border-box;`;
  }

  /**
   * Clears layout cache for window resize or orientation changes
   */
  public static invalidateCache(): void {
    this.cachedLayout = null;
  }
}
