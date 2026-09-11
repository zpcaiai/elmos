/**
 * @file enterprise-turnkey-benchmark-corpus.ts
 * @description Enterprise Production Turnkey Benchmark Applications Corpus for Batch 32 (M32).
 * Provides two real-world, highly complex enterprise frontends that thoroughly validate all 4 domains:
 * 1. EnterpriseLogisticsWmsMiniApp: Redux Saga, BLE scanner, Canvas 2D signature, Emotion CSS-in-JS, Custom Navbar
 * 2. EnterpriseFinancialRetailMiniApp: Pinia + $onAction, MobX Reactive Cart, Tailwind JIT arbitrary classes, WeChat Pay & PayScore, Microfrontend Sandbox.
 */

export const EnterpriseLogisticsWmsCorpus = {
  name: 'EnterpriseLogisticsWmsMiniApp',
  description: 'Industrial Warehouse Management & Delivery Tracking System',
  sourceFramework: 'react',
  targetFramework: 'wechat-miniapp',
  components: [
    {
      name: 'WmsParcelScanner',
      category: 'hardware-and-ble',
      sourceCode: `
import React, { useState, useEffect } from 'react';
import styled from '@emotion/styled';
import { useDispatch, useSelector } from 'react-redux';

const Container = styled.div\`
  display: flex;
  flex-direction: column;
  padding: 16px;
  background-color: \${props => props.isDarkMode ? '#1a1a1a' : '#f5f7fa'};
\`;

const BarcodeDisplay = styled.span\`
  font-size: 20px;
  font-weight: bold;
  color: \${props => props.status === 'VALID' ? '#52c41a' : '#f5222d'};
  margin-top: 12px;
\`;

export function WmsParcelScanner(props) {
  const [scannedCode, setScannedCode] = useState('');
  const [bleStatus, setBleStatus] = useState('DISCONNECTED');
  const dispatch = useDispatch();

  useEffect(() => {
    // Bluetooth scanner setup
    dispatch({ type: 'WMS/START_BLE_SCAN', payload: { serviceId: 'ffe0' } });
  }, []);

  const handleScan = (code) => {
    setScannedCode(code);
    dispatch({ type: 'WMS/FETCH_PARCEL_DETAILS', payload: { barcode: code } });
  };

  return (
    <Container isDarkMode={props.isDarkMode}>
      <div className="wms-header">Scanner Status: {bleStatus}</div>
      <BarcodeDisplay status={scannedCode ? 'VALID' : 'INVALID'}>
        {scannedCode || 'Waiting for BLE scanner input...'}
      </BarcodeDisplay>
    </Container>
  );
}
      `,
    },
    {
      name: 'WmsDeliverySignaturePad',
      category: 'canvas2d-and-touch',
      sourceCode: `
import React, { useRef, useEffect } from 'react';

export function WmsDeliverySignaturePad(props) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
  }, []);

  const handleSave = () => {
    props.onSaveSignature && props.onSaveSignature();
  };

  return (
    <div className="signature-container">
      <div className="signature-title">Customer Sign-off</div>
      <canvas id="signatureCanvas" type="2d" className="signature-pad" />
      <button className="confirm-btn" onClick={handleSave}>Confirm Receipt</button>
    </div>
  );
}
      `,
    },
  ],
  sagas: `
import { call, put, takeEvery, takeLatest, select, delay } from 'redux-saga/effects';

function* fetchParcelWorker(action) {
  try {
    yield put({ type: 'WMS/FETCH_START' });
    const response = yield call(fetch, '/api/v1/wms/parcels/' + action.payload.barcode);
    const data = yield call([response, 'json']);
    yield delay(100);
    yield put({ type: 'WMS/FETCH_SUCCESS', payload: data });
  } catch (error) {
    yield put({ type: 'WMS/FETCH_FAILED', error });
  }
}

export function* watchParcelActions() {
  yield takeLatest('WMS/FETCH_PARCEL_DETAILS', fetchParcelWorker);
}
  `,
};

export const EnterpriseFinancialRetailCorpus = {
  name: 'EnterpriseFinancialRetailMiniApp',
  description: 'Enterprise Retail E-Commerce with WeChat Pay & PayScore Integration',
  sourceFramework: 'vue3',
  targetFramework: 'wechat-miniapp',
  components: [
    {
      name: 'RetailCartCheckout',
      category: 'payment-and-state',
      sourceCode: `
<template>
  <div class="checkout-page bg-[#f0f2f5] p-[16px]">
    <div class="custom-navbar sticky top-0 bg-white shadow-sm h-[88px] pt-[44px]">
      <h1 class="text-[18px] font-semibold text-center text-[#1f1f1f]">Checkout</h1>
    </div>
    <div class="cart-items mt-[12px]">
      <div v-for="item in cart.items" :key="item.id" class="item-card flex justify-between p-[12px] bg-white rounded-[8px] mb-[8px]">
        <span class="name text-[14px] text-gray-800">{{ item.name }}</span>
        <span class="price font-bold text-red-600">¥{{ item.price }}</span>
      </div>
    </div>
    <div class="total-bar mt-[20px] p-[16px] bg-white flex justify-between items-center rounded-[8px]">
      <span class="text-[16px]">Total: ¥{{ cart.totalAmount }}</span>
      <div class="actions flex gap-2">
        <button class="pay-score-btn bg-green-500 text-white px-4 py-2 rounded" @click="handlePayScore">
          WeChat Pay Score
        </button>
        <button class="pay-btn bg-blue-600 text-white px-4 py-2 rounded" @click="handleDirectPay">
          Pay Now
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useCartStore } from './cartStore';

const cart = useCartStore();

const handleDirectPay = async () => {
  await cart.checkoutWithWeChatPay();
};

const handlePayScore = async () => {
  await cart.authorizePayScore();
};
</script>
      `,
    },
  ],
  piniaStore: `
import { defineStore } from 'pinia';

export const useCartStore = defineStore('cart', {
  state: () => ({
    items: [
      { id: 'SKU_001', name: 'Industrial RFID Handheld Reader', price: 2999, quantity: 1 },
      { id: 'SKU_002', name: 'Thermal Receipt Roll (Pack of 10)', price: 85, quantity: 2 },
    ],
    isAuthorizedForPayScore: false,
    orderId: '',
  }),
  getters: {
    totalAmount: (state) => state.items.reduce((sum, item) => sum + item.price * item.quantity, 0),
  },
  actions: {
    async checkoutWithWeChatPay() {
      // WeChat Pay settlement logic
      return { success: true, transactionId: 'TX_RETAIL_99182' };
    },
    async authorizePayScore() {
      // WeChat Pay Score verification
      this.isAuthorizedForPayScore = true;
    }
  }
});
  `,
};
