/**
 * @file cross-platform-hardware-native-sdk.test.ts
 * @description Comprehensive unit & integration tests for Cross-Platform Native SDK & Hardware APIs:
 * Bluetooth Low Energy (BLE), Camera Stream & QR scanning, Canvas 2D, WeChat Pay & PayScore, Custom Navbar.
 */

import {
  CrossPlatformBleEngine,
  CrossPlatformCameraEngine,
  CrossPlatformCanvas2dEngine,
  CrossPlatformPaymentEngine,
  CrossPlatformNavBarEngine,
} from '../src/runtime/hardware';

describe('Cross-Platform Native SDK & Hardware API Engine (M32)', () => {
  describe('Bluetooth Low Energy (BLE 4.0/5.0) Engine', () => {
    it('should open adapter, discover peripherals, connect, and read/write characteristics', async () => {
      const ble = new CrossPlatformBleEngine(true); // mock mode

      const discovered: any[] = [];
      const notifications: any[] = [];

      ble.setEventListeners({
        onDeviceFound: (dev) => discovered.push(dev),
        onCharacteristicValueChange: (devId, svcId, charId, val) => {
          notifications.push({ devId, svcId, charId, val });
        },
      });

      await ble.openAdapter();
      await ble.startScan(['0000ffe0-0000-1000-8000-00805f9b34fb']);

      expect(discovered.length).toBe(1);
      const targetDev = discovered[0]!;
      expect(targetDev.deviceId).toBe('MOCK_BLE_DEVICE_01');
      expect(targetDev.name).toContain('Enterprise POS Printer');

      await ble.connect(targetDev.deviceId);
      expect(ble.isConnected(targetDev.deviceId)).toBe(true);

      const services = await ble.getServices(targetDev.deviceId);
      expect(services.length).toBe(1);
      expect(services[0]?.uuid).toBe('0000ffe0-0000-1000-8000-00805f9b34fb');

      const chars = await ble.getCharacteristics(targetDev.deviceId, services[0]!.uuid);
      expect(chars.length).toBe(1);
      expect(chars[0]?.uuid).toBe('0000ffe1-0000-1000-8000-00805f9b34fb');
      expect(chars[0]?.properties.write).toBe(true);

      const payload = new Uint8Array([0x1b, 0x40, 0x41]).buffer; // ESC/POS print command
      await ble.writeValue(targetDev.deviceId, services[0]!.uuid, chars[0]!.uuid, payload);

      expect(notifications.length).toBe(1);
      expect(notifications[0]?.charId).toBe(chars[0]!.uuid);

      await ble.closeAdapter();
      expect(ble.isConnected(targetDev.deviceId)).toBe(false);
    });
  });

  describe('Camera Stream & Barcode Scanner Engine', () => {
    it('should scan barcodes and capture photo frames', async () => {
      const camera = new CrossPlatformCameraEngine(true);

      const scanRes = await camera.scanCode();
      expect(scanRes.rawValue).toContain('WMS/ITEMS/889201');
      expect(scanRes.format).toBe('qr_code');

      const photo = await camera.takePhoto('high');
      expect(photo.width).toBe(1920);
      expect(photo.height).toBe(1080);
      expect(photo.tempFilePath).toBeDefined();
    });
  });

  describe('High-Performance Canvas 2D Engine', () => {
    it('should initialize 2D context, apply DPR scaling, and normalize touch coordinates', async () => {
      const canvasEngine = new CrossPlatformCanvas2dEngine();
      const ctx = await canvasEngine.init('#myCanvas');

      expect(ctx).toBeDefined();
      const dims = canvasEngine.getDimensions();
      expect(dims.width).toBeGreaterThan(0);
      expect(dims.height).toBeGreaterThan(0);

      // Coordinate normalization
      const mockTouch = { touches: [{ x: 120, y: 85 }] };
      const coords = canvasEngine.normalizeEventCoordinates(mockTouch);
      expect(coords).toEqual({ x: 120, y: 85 });

      const imageUri = await canvasEngine.exportToImage();
      expect(imageUri).toBeDefined();
    });
  });

  describe('WeChat Pay & WeChat Pay Score Engine', () => {
    it('should process payment and authorize WeChat Pay Score', async () => {
      const payment = new CrossPlatformPaymentEngine(true);

      const receipt = await payment.requestPayment({
        timeStamp: '1690000000',
        nonceStr: 'random_nonce_123',
        package: 'prepay_id=wx123456789',
        signType: 'RSA',
        paySign: 'mock_signature',
      });

      expect(receipt.status).toBe('SUCCESS');
      expect(receipt.transactionId).toContain('TX_');
      expect(receipt.paidAmountCents).toBe(9900);

      const scoreRes = await payment.requestPayScore({
        businessType: 'wxpayScoreEnable',
        queryString: 'mch_id=123&service_id=888',
      });

      expect(scoreRes.status).toBe('SUCCESS');
      expect(scoreRes.extraData.service_order_no).toBe('PAYSCORE_ORD_99182');
    });
  });

  describe('Custom Navigation Bar & Safe Area Engine', () => {
    it('should calculate navigation layout with capsule button and safe area padding', () => {
      CrossPlatformNavBarEngine.invalidateCache();
      const layout = CrossPlatformNavBarEngine.getLayout();

      expect(layout.statusBarHeight).toBeGreaterThan(0);
      expect(layout.navBarHeight).toBeGreaterThan(0);
      expect(layout.totalHeaderHeight).toBe(layout.statusBarHeight + layout.navBarHeight);
      expect(layout.capsuleMetrics).toBeDefined();
      expect(layout.safeAreaTop).toBeGreaterThanOrEqual(layout.statusBarHeight);

      const styleStr = CrossPlatformNavBarEngine.getHeaderStyleString();
      expect(styleStr).toContain(`height: ${layout.totalHeaderHeight}px;`);
      expect(styleStr).toContain(`padding-top: ${layout.statusBarHeight}px;`);
    });
  });
});
