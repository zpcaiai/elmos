/**
 * @file layout-engine.test.ts
 * @description Comprehensive unit and integration test suite for Enterprise Layout & Responsive Engine.
 * Verifies GridFlexAdapter, ResponsiveContainerCompiler, Ant Design / Element Plus grid synthesis,
 * pure CSS Grid / Flexbox lowering, WeChat MiniApp flex layout, ArkUI declarative layout,
 * fluid typography clamp calculation, and container query synthesis.
 * Conforms to Batch 32 Skill 1218.
 */

import {
  UniversalLayoutIR,
  LayoutContainerIR,
  DEFAULT_BREAKPOINT_TIERS,
  GridFlexAdapter,
  ResponsiveContainerCompiler,
} from '../src/layout-engine';

describe('Enterprise Layout & Responsive Breakpoint Engine', () => {
  const adapter = new GridFlexAdapter();
  const compiler = new ResponsiveContainerCompiler();

  const sampleLayout: UniversalLayoutIR = {
    version: '1.0',
    documentName: 'DashboardResponsiveView',
    gridBaseSystem: 24,
    breakpointConfig: DEFAULT_BREAKPOINT_TIERS,
    rootContainer: {
      id: 'root_grid',
      kind: 'row',
      display: 'flex',
      direction: { xs: 'column', md: 'row' },
      wrap: 'wrap',
      gap: { xs: 8, md: 16, lg: 24 },
      children: [
        {
          id: 'sidebar_col',
          kind: 'col',
          span: { xs: 24, sm: 8, md: 6, lg: 4 },
          componentTag: 'AppSidebar',
          contentCode: '<AppSidebar />',
        },
        {
          id: 'content_col',
          kind: 'col',
          span: { xs: 24, sm: 16, md: 18, lg: 20 },
          componentTag: 'MainContent',
          contentCode: '<MainContent />',
          containerConditions: [
            {
              minWidth: 600,
              styleOverrides: {
                padding: '24px',
                backgroundColor: '#f8fafc',
              },
            },
          ],
        },
      ],
    },
    fluidTypography: {
      minViewport: 375,
      maxViewport: 1440,
      minFontSize: 14,
      maxFontSize: 20,
    },
  };

  describe('GridFlexAdapter - Normalization and Breakpoints', () => {
    it('should normalize scalar value across all breakpoint tiers', () => {
      const normalized = GridFlexAdapter.normalizeResponsive(12, 24);
      expect(normalized.xs).toBe(12);
      expect(normalized.sm).toBe(12);
      expect(normalized.md).toBe(12);
      expect(normalized.lg).toBe(12);
      expect(normalized.xl).toBe(12);
      expect(normalized.xxl).toBe(12);
    });

    it('should cascade specified responsive values to larger breakpoints', () => {
      const normalized = GridFlexAdapter.normalizeResponsive({ xs: 24, md: 12 }, 24);
      expect(normalized.xs).toBe(24);
      expect(normalized.sm).toBe(24); // inherits xs
      expect(normalized.md).toBe(12);
      expect(normalized.lg).toBe(12); // inherits md
      expect(normalized.xl).toBe(12);
    });
  });

  describe('GridFlexAdapter - Framework Emitters', () => {
    it('should compile layout to Ant Design React Grid JSX', () => {
      const res = adapter.emitAntDesignGrid(sampleLayout);
      expect(res.targetFramework).toBe('ant-design-grid');
      expect(res.code).toContain(`<Row`);
      expect(res.code).toContain(`<Col`);
      expect(res.code).toContain(`xs={24}`);
      expect(res.code).toContain(`md={6}`);
      expect(res.metrics.containersCount).toBeGreaterThanOrEqual(1);
      expect(res.metrics.itemsCount).toBe(2);
      expect(res.warnings.length).toBe(0);
    });

    it('should compile layout to Element Plus Vue 3 template', () => {
      const res = adapter.emitElementPlusGrid(sampleLayout);
      expect(res.targetFramework).toBe('element-plus-grid');
      expect(res.code).toContain(`<el-row`);
      expect(res.code).toContain(`<el-col`);
      expect(res.code).toContain(`:xs="24"`);
      expect(res.code).toContain(`:md="6"`);
      expect(res.metrics.itemsCount).toBe(2);
    });

    it('should compile layout to Pure CSS Grid with media queries', () => {
      const res = adapter.emitPureCSSGrid(sampleLayout);
      expect(res.targetFramework).toBe('css-grid');
      expect(res.code).toContain(`cssgrid-dashboardresponsiveview`);
      expect(res.styleCode).toContain(`display: grid;`);
      expect(res.mediaQueriesCss).toBeDefined();
      expect(res.mediaQueriesCss).toContain(`@media (min-width: 768px)`);
    });

    it('should compile layout to WeChat MiniApp WXML & WXSS flex layout', () => {
      const res = adapter.emitMiniAppFlex(sampleLayout);
      expect(res.targetFramework).toBe('miniapp-flex');
      expect(res.code).toContain(`miniapp-layout-dashboardresponsiveview`);
      expect(res.styleCode).toContain(`display: flex;`);
      expect(res.styleCode).toContain(`flex-wrap: wrap;`);
    });

    it('should compile layout to ArkUI declarative layout components', () => {
      const res = adapter.emitArkUILayout(sampleLayout);
      expect(res.targetFramework).toBe('arkui-layout');
      expect(res.code).toContain(`Flex({ wrap: FlexWrap.Wrap`);
      expect(res.code).toContain(`Column()`);
    });
  });

  describe('ResponsiveContainerCompiler - Fluid Typography and Container Queries', () => {
    it('should compute CSS clamp() expression for fluid typography', () => {
      const clampExpr = ResponsiveContainerCompiler.computeFluidClamp({
        minViewportPx: 375,
        maxViewportPx: 1440,
        minSizePx: 14,
        maxSizePx: 20,
      });

      expect(clampExpr).toMatch(/^clamp\(0\.875rem, .+vw \+ .+rem, 1\.25rem\)$/);
    });

    it('should synthesize modern CSS Container Queries for responsive sub-containers', () => {
      const res = compiler.synthesizeContainerQueries(sampleLayout.rootContainer);
      expect(res.containerCss).toContain(`container-type: inline-size;`);
      expect(res.itemRulesCss).toContain(`(min-width: 600px)`);
      expect(res.itemRulesCss).toContain(`background-color: #f8fafc;`);
    });

    it('should validate layout correctness and flag span overflows when nowrap is set', () => {
      const validRes = compiler.validateLayout(sampleLayout);
      expect(validRes.isValid).toBe(true);
      expect(validRes.errors.length).toBe(0);

      const invalidLayout: UniversalLayoutIR = {
        ...sampleLayout,
        rootContainer: {
          ...sampleLayout.rootContainer,
          wrap: 'nowrap',
          children: [
            {
              id: 'col_1',
              kind: 'col',
              span: 16,
            },
            {
              id: 'col_2',
              kind: 'col',
              span: 16, // 16 + 16 = 32 > 24 with nowrap!
            },
          ],
        },
      };

      const invalidRes = compiler.validateLayout(invalidLayout);
      expect(invalidRes.isValid).toBe(false);
      expect(invalidRes.errors.length).toBeGreaterThan(0);
      expect(invalidRes.errors[0]).toContain('exceeds grid base (24)');
    });
  });
});
