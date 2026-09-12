/**
 * @file enterprise-ui-library-engine.test.ts
 * @description Comprehensive Jest test suite for Enterprise UI Library Translation Engine (Skills 1208 & 1217).
 * Tests automated cross-library translation between Ant Design, Element Plus, and Vant Weapp.
 * Conforms to Batch 32 Skills 1208 & 1217.
 */

import { EnterpriseUILibraryEngine } from '../src/ui-library-engine/enterprise-ui-library-engine';
import { AntDesignAdapter } from '../src/ui-library-engine/ant-design-adapter';
import { ElementPlusAdapter } from '../src/ui-library-engine/element-plus-adapter';
import { VantTDesignAdapter } from '../src/ui-library-engine/vant-tdesign-adapter';

describe('Enterprise UI Library Translation Engine (Skills 1208 & 1217)', () => {
  const engine = new EnterpriseUILibraryEngine();

  const sampleAntDJSX = `
import React from 'react';
import { Button, Input, Modal, Card, Alert, Tag } from 'antd';

export const AdminPanel = () => {
  return (
    <Card title="Management">
      <Alert message="System online" type="success" showIcon />
      <Input placeholder="Enter username" allowClear />
      <Button type="primary" loading={false}>
        Save Changes
      </Button>
      <Tag color="success">Active</Tag>
    </Card>
  );
};
`;

  it('should find registered component mapping rules across libraries', () => {
    const btnRule = engine.findRule('ant-design', 'Button', 'element-plus');
    expect(btnRule).toBeDefined();
    expect(btnRule?.targetComponentName).toBe('el-button');
    expect(btnRule?.canonicalType).toBe('button');

    const inputRule = engine.findRule('ant-design', 'Input', 'element-plus');
    expect(inputRule).toBeDefined();
    expect(inputRule?.targetComponentName).toBe('el-input');

    const vantBtnRule = engine.findRule('ant-design', 'Button', 'vant');
    expect(vantBtnRule).toBeDefined();
    expect(vantBtnRule?.targetComponentName).toBe('van-button');
  });

  it('should transform Ant Design components to Element Plus components with prop remapping', () => {
    const res = engine.transformJSX(sampleAntDJSX, 'ant-design', 'element-plus');

    expect(res.matchedComponents.length).toBeGreaterThan(0);
    expect(res.transformedCode).toContain('<el-card');
    expect(res.transformedCode).toContain('header="Management"');
    expect(res.transformedCode).toContain('<el-alert');
    expect(res.transformedCode).toContain('title="System online"');
    expect(res.transformedCode).toContain('<el-input');
    expect(res.transformedCode).toContain('clearable');
    expect(res.transformedCode).toContain('<el-button');
    expect(res.transformedCode).toContain('type="primary"');
    expect(res.transformedCode).toContain('<el-tag');
  });

  it('should adjust imports from antd to element-plus', () => {
    const res = engine.transformJSX(sampleAntDJSX, 'ant-design', 'element-plus');

    expect(res.transformedCode).not.toContain("from 'antd'");
    expect(res.transformedCode).toContain("from 'element-plus'");
    expect(res.addedImports.some((i) => i.module === 'element-plus')).toBe(true);
  });

  it('should transform Ant Design components to Vant Weapp MiniApp components', () => {
    const res = engine.transformJSX(sampleAntDJSX, 'ant-design', 'vant');

    expect(res.transformedCode).toContain('<van-button');
    expect(res.transformedCode).toContain('<van-field');
    expect(res.transformedCode).toContain('<van-panel');
  });

  it('should support reverse mapping from Element Plus to Ant Design', () => {
    const sampleElPlusJSX = `
<ElButton type="primary" size="small">Submit</ElButton>
`;
    const res = engine.transformJSX(sampleElPlusJSX, 'element-plus', 'ant-design');
    expect(res.transformedCode).toContain('<Button');
    expect(res.transformedCode).toContain('size="small"');
  });
});
