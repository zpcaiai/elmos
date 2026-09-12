import {
  DOMNode,
  HTMLParser,
  HeadlessBoxLayoutEngine,
  MiniAppSSREvaluator,
  WebSSREvaluator,
  UniversalDOMDifferentialEngine
} from '../src/headless-differential-suite';

describe('Headless Browser & MiniApp SSR DOM Differential Verification Suite', () => {
  describe('Headless Virtual DOM & HTML Parser', () => {
    it('parses nested HTML strings into DOMNode tree', () => {
      const html = `
        <div class="container main-card" id="card-1">
          <h2 class="title">Product Overview</h2>
          <p class="desc">A high performance migration platform.</p>
          <button type="submit" disabled>Execute</button>
        </div>
      `;

      const nodes = HTMLParser.parse(html);
      expect(nodes.length).toBe(1);
      const root = nodes[0]!;
      expect(root.tagName).toBe('div');
      expect(root.hasClass('container')).toBe(true);
      expect(root.hasClass('main-card')).toBe(true);
      expect(root.getAttribute('id')).toBe('card-1');

      const titleNode = root.querySelector('.title');
      expect(titleNode).not.toBeNull();
      expect(titleNode?.textContent).toBe('Product Overview');

      const btn = root.querySelector('button');
      expect(btn).not.toBeNull();
      expect(btn?.getAttribute('type')).toBe('submit');
      expect(btn?.getAttribute('disabled')).toBe('');
    });

    it('computes 2D box layout for block and flex containers', () => {
      const root = new DOMNode('element', 'div');
      root.style['display'] = 'flex';
      root.style['flex-direction'] = 'row';

      const child1 = new DOMNode('element', 'div');
      child1.style['width'] = '100px';
      child1.style['height'] = '50px';

      const child2 = new DOMNode('element', 'div');
      child2.style['width'] = '150px';
      child2.style['height'] = '80px';

      root.appendChild(child1);
      root.appendChild(child2);

      HeadlessBoxLayoutEngine.computeLayout(root, 375, 667);

      expect(child1.computedLayout?.rect.width).toBe(100);
      expect(child1.computedLayout?.rect.height).toBe(50);
      expect(child2.computedLayout?.rect.x).toBe(100);
      expect(child2.computedLayout?.rect.width).toBe(150);
      expect(root.computedLayout?.rect.width).toBe(250);
    });
  });

  describe('MiniApp SSR Evaluator', () => {
    const miniappSource = {
      wxml: `
        <view class="account-panel">
          <view class="header">
            <text class="user-name">{{userInfo.name}}</text>
            <text class="balance">{{balanceText}}</text>
          </view>
          <view wx:if="{{showNotice}}" class="notice-bar">
            <text>System Maintenance Tonight</text>
          </view>
          <view class="tx-list">
            <view wx:for="{{transactions}}" wx:key="id" class="tx-item">
              <text class="tx-title">{{item.title}}</text>
              <text class="tx-amount">{{item.amount}}</text>
            </view>
          </view>
        </view>
      `,
      js: `
        Component({
          data: {
            balanceText: '$1,250.00',
            showNotice: true
          }
        });
      `
    };

    it('evaluates WXML directives, bindings, and generates DOMNode tree', () => {
      const renderContext = {
        props: {
          userInfo: { name: 'Alice Chen' },
          transactions: [
            { id: '1', title: 'Coffee', amount: '-$4.50' },
            { id: '2', title: 'Salary', amount: '+$3,000.00' }
          ]
        }
      };

      const domTree = MiniAppSSREvaluator.evaluate(miniappSource, renderContext);
      expect(domTree).toBeDefined();

      const text = domTree.textContent;
      expect(text).toContain('Alice Chen');
      expect(text).toContain('$1,250.00');
      expect(text).toContain('System Maintenance Tonight');
      expect(text).toContain('Coffee');
      expect(text).toContain('-$4.50');
      expect(text).toContain('Salary');
    });

    it('handles conditional wx:if false branches correctly', () => {
      const context = {
        props: {
          userInfo: { name: 'Bob' },
          transactions: []
        },
        state: {
          showNotice: false
        }
      };

      const domTree = MiniAppSSREvaluator.evaluate(miniappSource, context);
      expect(domTree.textContent).not.toContain('System Maintenance Tonight');
    });
  });

  describe('Universal DOM Differential Engine & Quality Gates', () => {
    it('compares equivalent Web and MiniApp components and passes L4 Semantic Gate', () => {
      // Source Web Component HTML
      const webHtml = `
        <div class="user-profile">
          <div class="header">
            <span class="name">Stephen Hawking</span>
            <span class="role">Admin</span>
          </div>
          <p class="bio">Theoretical Physicist</p>
          <button type="button" class="btn-action">Edit Profile</button>
        </div>
      `;

      // Target MiniApp Transpiled Output
      const miniappFiles = {
        wxml: `
          <view class="user-profile">
            <view class="header">
              <text class="name">Stephen Hawking</text>
              <text class="role">Admin</text>
            </view>
            <text class="bio">Theoretical Physicist</text>
            <button type="button" class="btn-action">Edit Profile</button>
          </view>
        `
      };

      const webDOM = WebSSREvaluator.evaluateHTML(webHtml);
      const miniappDOM = MiniAppSSREvaluator.evaluate(miniappFiles);

      const verdict = UniversalDOMDifferentialEngine.compare(webDOM, miniappDOM);

      expect(verdict.passed).toBe(true);
      expect(verdict.l3Passed).toBe(true);
      expect(verdict.l4Passed).toBe(true);
      expect(verdict.tier).toBe('L4_SEMANTIC_EQUIVALENT');
      expect(verdict.scores.structuralScore).toBeGreaterThanOrEqual(0.95);
      expect(verdict.scores.contentScore).toBe(1.0);
      expect(verdict.scores.compositeScore).toBeGreaterThanOrEqual(0.95);
      expect(verdict.fatalCount).toBe(0);
    });

    it('detects structural and content divergence and fails L4 gate', () => {
      const webHtml = `
        <div class="dashboard">
          <h1>Analytics Cockpit</h1>
          <div class="kpi-card">Revenue: $100,000</div>
          <div class="kpi-card">Growth: +25%</div>
        </div>
      `;

      // Flawed miniapp component missing kpi-card
      const miniappFiles = {
        wxml: `
          <view class="dashboard">
            <text>Analytics Cockpit</text>
            <view class="notice">Data currently unavailable</view>
          </view>
        `
      };

      const webDOM = WebSSREvaluator.evaluateHTML(webHtml);
      const miniappDOM = MiniAppSSREvaluator.evaluate(miniappFiles);

      const verdict = UniversalDOMDifferentialEngine.compare(webDOM, miniappDOM);

      expect(verdict.l4Passed).toBe(false);
      expect(verdict.totalMismatches).toBeGreaterThan(0);
    });
  });
});
