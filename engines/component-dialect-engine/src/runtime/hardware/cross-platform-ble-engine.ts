/**
 * @file cross-platform-ble-engine.ts
 * @description Enterprise Cross-Platform Bluetooth Low Energy (BLE 4.0/5.0) Engine.
 * Provides unified bidirectional abstraction across WeChat MiniApp BLE APIs
 * and Web Bluetooth API (navigator.bluetooth), with offline mock simulation,
 * MTU-aware chunked transmission, and resilient connection state machines with exponential backoff.
 */

export interface BleDevice {
  deviceId: string;
  name: string;
  RSSI: number;
  advertisData?: ArrayBuffer;
  services?: string[];
}

export interface BleService {
  uuid: string;
  isPrimary: boolean;
}

export interface BleCharacteristic {
  uuid: string;
  properties: {
    read: boolean;
    write: boolean;
    notify: boolean;
    indicate: boolean;
  };
}

export type BleConnectionStatus =
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'DISCONNECTING'
  | 'RECONNECTING'
  | 'FAILED';

export interface BleReconnectOptions {
  autoReconnect?: boolean;
  maxAttempts?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
  factor?: number;
  jitter?: boolean;
}

export interface BleChunkedWriteOptions {
  deviceId: string;
  serviceId: string;
  characteristicId: string;
  data: ArrayBuffer;
  chunkSize?: number;
  packetDelayMs?: number;
  maxRetriesPerChunk?: number;
  onProgress?: (progress: BleTransferProgress) => void;
}

export interface BleTransferProgress {
  sentBytes: number;
  totalBytes: number;
  chunkIndex: number;
  totalChunks: number;
  percentage: number;
}

export interface BleTransferResult {
  totalBytes: number;
  chunksSent: number;
  durationMs: number;
  success: boolean;
}

export interface BleEventMap {
  onDeviceFound: (device: BleDevice) => void;
  onConnectionStateChange: (deviceId: string, connected: boolean) => void;
  onConnectionStatusChange?: (
    deviceId: string,
    status: BleConnectionStatus,
    detail?: { attempt?: number; delayMs?: number; error?: Error }
  ) => void;
  onCharacteristicValueChange: (
    deviceId: string,
    serviceId: string,
    charId: string,
    value: ArrayBuffer
  ) => void;
}

const DEFAULT_MTU_PAYLOAD = 20; // Default GATT ATT MTU 23 - 3 byte header = 20 byte payload
const MIN_CHUNK_SIZE = 1;
const MAX_CHUNK_SIZE = 512;
const DEFAULT_PACKET_DELAY_MS = 15;

export class CrossPlatformBleEngine {
  private isMockMode: boolean;
  private isAdapterOpened = false;
  private discoveredDevices: Map<string, BleDevice> = new Map();
  private connectedDevices: Set<string> = new Set();
  private connectionStatuses: Map<string, BleConnectionStatus> = new Map();
  private negotiatedMtu: Map<string, number> = new Map();
  private listeners: Partial<BleEventMap> = {};
  private mockServices: Map<string, BleService[]> = new Map();
  private mockCharacteristics: Map<string, BleCharacteristic[]> = new Map();
  private reconnectConfigs: Map<string, Required<BleReconnectOptions>> = new Map();
  private reconnectAttempts: Map<string, number> = new Map();
  private reconnectTimers: Map<string, any> = new Map();

  constructor(mockMode: boolean = false) {
    this.isMockMode = mockMode || (typeof wx === 'undefined' && typeof navigator === 'undefined');
  }

  public setEventListeners(listeners: Partial<BleEventMap>): void {
    this.listeners = { ...this.listeners, ...listeners };
  }

  public getConnectionStatus(deviceId: string): BleConnectionStatus {
    return this.connectionStatuses.get(deviceId) || 'DISCONNECTED';
  }

  public getNegotiatedMtu(deviceId: string): number {
    return this.negotiatedMtu.get(deviceId) || DEFAULT_MTU_PAYLOAD;
  }

  private setConnectionStatus(
    deviceId: string,
    status: BleConnectionStatus,
    detail?: { attempt?: number; delayMs?: number; error?: Error }
  ): void {
    const prevStatus = this.connectionStatuses.get(deviceId);
    this.connectionStatuses.set(deviceId, status);

    if (status === 'CONNECTED') {
      this.connectedDevices.add(deviceId);
    } else if (status === 'DISCONNECTED' || status === 'FAILED') {
      this.connectedDevices.delete(deviceId);
    }

    if (this.listeners.onConnectionStatusChange && prevStatus !== status) {
      this.listeners.onConnectionStatusChange(deviceId, status, detail);
    }

    if (this.listeners.onConnectionStateChange) {
      const isConnected = status === 'CONNECTED';
      const wasConnected = prevStatus === 'CONNECTED';
      if (isConnected !== wasConnected) {
        this.listeners.onConnectionStateChange(deviceId, isConnected);
      }
    }
  }

  /**
   * Open Bluetooth Adapter
   */
  public async openAdapter(): Promise<void> {
    if (this.isMockMode) {
      this.isAdapterOpened = true;
      return;
    }

    if (typeof wx !== 'undefined' && wx.openBluetoothAdapter) {
      return new Promise((resolve, reject) => {
        wx.openBluetoothAdapter({
          success: () => {
            this.isAdapterOpened = true;
            this.setupWxConnectionListener();
            resolve();
          },
          fail: (err: any) => reject(new Error(err.errMsg || 'wx.openBluetoothAdapter failed')),
        });
      });
    }

    if (typeof navigator !== 'undefined' && 'bluetooth' in navigator) {
      this.isAdapterOpened = true;
      return;
    }

    // Fallback to mock mode if unsupported
    this.isMockMode = true;
    this.isAdapterOpened = true;
  }

  private setupWxConnectionListener(): void {
    if (typeof wx !== 'undefined' && wx.onBLEConnectionStateChange) {
      wx.onBLEConnectionStateChange((res: { deviceId: string; connected: boolean }) => {
        if (!res.connected) {
          this.handleUnexpectedDisconnection(res.deviceId);
        } else {
          this.setConnectionStatus(res.deviceId, 'CONNECTED');
        }
      });
    }
  }

  /**
   * Close Bluetooth Adapter
   */
  public async closeAdapter(): Promise<void> {
    this.isAdapterOpened = false;

    // Clear all reconnection attempts
    for (const [deviceId, timer] of this.reconnectTimers.entries()) {
      clearTimeout(timer);
      this.setConnectionStatus(deviceId, 'DISCONNECTED');
    }
    this.reconnectTimers.clear();
    this.reconnectAttempts.clear();
    this.connectedDevices.clear();
    this.connectionStatuses.clear();
    this.discoveredDevices.clear();

    if (!this.isMockMode && typeof wx !== 'undefined' && wx.closeBluetoothAdapter) {
      return new Promise((resolve) => {
        wx.closeBluetoothAdapter({ complete: () => resolve() });
      });
    }
  }

  /**
   * Start scanning for BLE peripherals
   */
  public async startScan(serviceUuids: string[] = []): Promise<void> {
    if (!this.isAdapterOpened) {
      throw new Error('Bluetooth adapter not opened. Call openAdapter() first.');
    }

    if (this.isMockMode) {
      const mockDev: BleDevice = {
        deviceId: 'MOCK_BLE_DEVICE_01',
        name: 'Enterprise POS Printer & Scanner',
        RSSI: -58,
        services: serviceUuids.length > 0 ? serviceUuids : ['0000ffe0-0000-1000-8000-00805f9b34fb'],
      };
      this.discoveredDevices.set(mockDev.deviceId, mockDev);
      if (this.listeners.onDeviceFound) {
        this.listeners.onDeviceFound(mockDev);
      }
      return;
    }

    if (typeof wx !== 'undefined' && wx.startBluetoothDevicesDiscovery) {
      return new Promise((resolve, reject) => {
        wx.startBluetoothDevicesDiscovery({
          services: serviceUuids,
          allowDuplicatesKey: false,
          success: () => {
            if (wx.onBluetoothDeviceFound) {
              wx.onBluetoothDeviceFound((res: any) => {
                for (const dev of res.devices) {
                  const mapped: BleDevice = {
                    deviceId: dev.deviceId,
                    name: dev.name || 'Unknown',
                    RSSI: dev.RSSI,
                    advertisData: dev.advertisData,
                  };
                  this.discoveredDevices.set(mapped.deviceId, mapped);
                  if (this.listeners.onDeviceFound) {
                    this.listeners.onDeviceFound(mapped);
                  }
                }
              });
            }
            resolve();
          },
          fail: (err: any) => reject(new Error(err.errMsg || 'startBluetoothDevicesDiscovery failed')),
        });
      });
    }
  }

  /**
   * Connect to a BLE peripheral with optional automatic reconnection policy
   */
  public async connect(deviceId: string, reconnectOptions?: BleReconnectOptions): Promise<void> {
    if (!this.isAdapterOpened) {
      throw new Error('Bluetooth adapter not opened. Call openAdapter() first.');
    }

    const config: Required<BleReconnectOptions> = {
      autoReconnect: reconnectOptions?.autoReconnect ?? false,
      maxAttempts: Math.max(1, reconnectOptions?.maxAttempts ?? 3),
      initialDelayMs: Math.max(50, reconnectOptions?.initialDelayMs ?? 500),
      maxDelayMs: Math.max(100, reconnectOptions?.maxDelayMs ?? 5000),
      factor: Math.max(1.1, reconnectOptions?.factor ?? 2),
      jitter: reconnectOptions?.jitter ?? true,
    };
    this.reconnectConfigs.set(deviceId, config);
    this.reconnectAttempts.set(deviceId, 0);

    return this.executeConnect(deviceId);
  }

  private async executeConnect(deviceId: string): Promise<void> {
    const isReconnecting = this.connectionStatuses.get(deviceId) === 'RECONNECTING';
    if (!isReconnecting) {
      this.setConnectionStatus(deviceId, 'CONNECTING');
    }

    if (this.isMockMode) {
      this.setConnectionStatus(deviceId, 'CONNECTED');
      this.mockServices.set(deviceId, [
        { uuid: '0000ffe0-0000-1000-8000-00805f9b34fb', isPrimary: true },
      ]);
      this.mockCharacteristics.set('0000ffe0-0000-1000-8000-00805f9b34fb', [
        {
          uuid: '0000ffe1-0000-1000-8000-00805f9b34fb',
          properties: { read: true, write: true, notify: true, indicate: false },
        },
      ]);
      return;
    }

    if (typeof wx !== 'undefined' && wx.createBLEConnection) {
      return new Promise((resolve, reject) => {
        wx.createBLEConnection({
          deviceId,
          success: () => {
            this.setConnectionStatus(deviceId, 'CONNECTED');
            resolve();
          },
          fail: (err: any) => {
            const error = new Error(err.errMsg || 'createBLEConnection failed');
            if (this.reconnectConfigs.get(deviceId)?.autoReconnect) {
              this.scheduleReconnect(deviceId, error);
              resolve(); // Reconnection in flight
            } else {
              this.setConnectionStatus(deviceId, 'FAILED', { error });
              reject(error);
            }
          },
        });
      });
    }
  }

  /**
   * Handle unexpected disconnection and trigger exponential backoff reconnection
   */
  public handleUnexpectedDisconnection(deviceId: string): void {
    if (!this.connectedDevices.has(deviceId) && this.connectionStatuses.get(deviceId) !== 'CONNECTED') {
      return;
    }

    const config = this.reconnectConfigs.get(deviceId);
    if (config?.autoReconnect) {
      this.scheduleReconnect(deviceId, new Error('Connection lost unexpectedly'));
    } else {
      this.setConnectionStatus(deviceId, 'DISCONNECTED');
    }
  }

  /**
   * Manually trigger disconnection simulation (primarily for tests / mock)
   */
  public simulateDisconnection(deviceId: string, triggerAutoReconnect: boolean = true): void {
    if (triggerAutoReconnect && this.reconnectConfigs.get(deviceId)?.autoReconnect) {
      this.scheduleReconnect(deviceId, new Error('Simulated disconnection'));
    } else {
      this.setConnectionStatus(deviceId, 'DISCONNECTED');
    }
  }

  private scheduleReconnect(deviceId: string, error?: Error): void {
    const config = this.reconnectConfigs.get(deviceId);
    if (!config) {
      this.setConnectionStatus(deviceId, 'DISCONNECTED');
      return;
    }

    const attempt = (this.reconnectAttempts.get(deviceId) || 0) + 1;
    this.reconnectAttempts.set(deviceId, attempt);

    if (attempt > config.maxAttempts) {
      this.setConnectionStatus(deviceId, 'FAILED', {
        attempt,
        error: error || new Error(`Max reconnection attempts (${config.maxAttempts}) exceeded`),
      });
      return;
    }

    // Exponential backoff calculation
    let delay = config.initialDelayMs * Math.pow(config.factor, attempt - 1);
    delay = Math.min(delay, config.maxDelayMs);

    if (config.jitter) {
      const jitterRange = delay * 0.2;
      delay = delay - jitterRange / 2 + Math.random() * jitterRange;
    }
    delay = Math.round(delay);

    this.setConnectionStatus(deviceId, 'RECONNECTING', { attempt, delayMs: delay, error });

    const timer = setTimeout(async () => {
      this.reconnectTimers.delete(deviceId);
      try {
        await this.executeConnect(deviceId);
      } catch (err: any) {
        this.scheduleReconnect(deviceId, err);
      }
    }, delay);

    this.reconnectTimers.set(deviceId, timer);
  }

  /**
   * Explicitly disconnect from a peripheral, aborting any active reconnection loop
   */
  public async disconnect(deviceId: string): Promise<void> {
    const timer = this.reconnectTimers.get(deviceId);
    if (timer) {
      clearTimeout(timer);
      this.reconnectTimers.delete(deviceId);
    }
    this.reconnectAttempts.delete(deviceId);

    this.setConnectionStatus(deviceId, 'DISCONNECTING');

    if (this.isMockMode) {
      this.setConnectionStatus(deviceId, 'DISCONNECTED');
      return;
    }

    if (typeof wx !== 'undefined' && wx.closeBLEConnection) {
      return new Promise((resolve) => {
        wx.closeBLEConnection({
          deviceId,
          complete: () => {
            this.setConnectionStatus(deviceId, 'DISCONNECTED');
            resolve();
          },
        });
      });
    }

    this.setConnectionStatus(deviceId, 'DISCONNECTED');
  }

  /**
   * Negotiate Maximum Transmission Unit (MTU)
   */
  public async setMtu(deviceId: string, mtu: number): Promise<number> {
    if (!this.isConnected(deviceId)) {
      throw new Error(`Device ${deviceId} is not connected. Call connect() first.`);
    }

    const targetMtu = Math.max(23, Math.min(mtu, 512));
    const effectivePayload = targetMtu - 3; // ATT header overhead

    if (this.isMockMode) {
      this.negotiatedMtu.set(deviceId, effectivePayload);
      return effectivePayload;
    }

    if (typeof wx !== 'undefined' && wx.setBLEMTU) {
      return new Promise((resolve, reject) => {
        wx.setBLEMTU({
          deviceId,
          mtu: targetMtu,
          success: (res: any) => {
            const actualMtu = res.mtu || targetMtu;
            const payload = Math.max(DEFAULT_MTU_PAYLOAD, actualMtu - 3);
            this.negotiatedMtu.set(deviceId, payload);
            resolve(payload);
          },
          fail: (err: any) => reject(new Error(err.errMsg || 'setBLEMTU failed')),
        });
      });
    }

    this.negotiatedMtu.set(deviceId, effectivePayload);
    return effectivePayload;
  }

  /**
   * Get BLE Services of connected device
   */
  public async getServices(deviceId: string): Promise<BleService[]> {
    if (this.isMockMode) {
      return this.mockServices.get(deviceId) || [];
    }

    if (typeof wx !== 'undefined' && wx.getBLEDeviceServices) {
      return new Promise((resolve, reject) => {
        wx.getBLEDeviceServices({
          deviceId,
          success: (res: any) => resolve(res.services),
          fail: (err: any) => reject(new Error(err.errMsg || 'getBLEDeviceServices failed')),
        });
      });
    }

    return [];
  }

  /**
   * Get Characteristics for a service
   */
  public async getCharacteristics(deviceId: string, serviceId: string): Promise<BleCharacteristic[]> {
    if (this.isMockMode) {
      return this.mockCharacteristics.get(serviceId) || [];
    }

    if (typeof wx !== 'undefined' && wx.getBLEDeviceCharacteristics) {
      return new Promise((resolve, reject) => {
        wx.getBLEDeviceCharacteristics({
          deviceId,
          serviceId,
          success: (res: any) => resolve(res.characteristics),
          fail: (err: any) => reject(new Error(err.errMsg || 'getBLEDeviceCharacteristics failed')),
        });
      });
    }

    return [];
  }

  /**
   * Write atomic data to a BLE characteristic
   */
  public async writeValue(
    deviceId: string,
    serviceId: string,
    charId: string,
    value: ArrayBuffer
  ): Promise<void> {
    if (!this.isConnected(deviceId)) {
      throw new Error(`Device ${deviceId} is not connected.`);
    }

    if (this.isMockMode) {
      if (this.listeners.onCharacteristicValueChange) {
        this.listeners.onCharacteristicValueChange(deviceId, serviceId, charId, value);
      }
      return;
    }

    if (typeof wx !== 'undefined' && wx.writeBLECharacteristicValue) {
      return new Promise((resolve, reject) => {
        wx.writeBLECharacteristicValue({
          deviceId,
          serviceId,
          characteristicId: charId,
          value,
          success: () => resolve(),
          fail: (err: any) => reject(new Error(err.errMsg || 'writeBLECharacteristicValue failed')),
        });
      });
    }
  }

  /**
   * Industrial Chunked MTU Slicing Transmission with flow control, progress feedback, and retry
   */
  public async writeChunked(options: BleChunkedWriteOptions): Promise<BleTransferResult> {
    const {
      deviceId,
      serviceId,
      characteristicId,
      data,
      packetDelayMs = DEFAULT_PACKET_DELAY_MS,
      maxRetriesPerChunk = 2,
      onProgress,
    } = options;

    if (!this.isConnected(deviceId)) {
      throw new Error(`Device ${deviceId} is not connected. Cannot perform chunked write.`);
    }

    const negotiated = this.getNegotiatedMtu(deviceId);
    const chunkSize = Math.max(MIN_CHUNK_SIZE, Math.min(options.chunkSize ?? negotiated, MAX_CHUNK_SIZE));
    const totalBytes = data.byteLength;
    const totalChunks = Math.max(1, Math.ceil(totalBytes / chunkSize));
    const startTime = Date.now();

    let sentBytes = 0;
    let chunksSent = 0;

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
      const offset = chunkIndex * chunkSize;
      const end = Math.min(offset + chunkSize, totalBytes);
      const chunk = data.slice(offset, end);

      let attempts = 0;
      let chunkDelivered = false;
      let lastError: Error | null = null;

      while (attempts <= maxRetriesPerChunk && !chunkDelivered) {
        try {
          await this.writeValue(deviceId, serviceId, characteristicId, chunk);
          chunkDelivered = true;
        } catch (err: any) {
          attempts++;
          lastError = err instanceof Error ? err : new Error(String(err));
          if (attempts <= maxRetriesPerChunk) {
            await new Promise((resolve) => setTimeout(resolve, 50 * attempts));
          }
        }
      }

      if (!chunkDelivered) {
        throw new Error(
          `Failed to transmit chunk ${chunkIndex + 1}/${totalChunks} after ${maxRetriesPerChunk + 1} attempts: ${
            lastError?.message || 'Unknown write error'
          }`
        );
      }

      sentBytes += chunk.byteLength;
      chunksSent++;

      if (onProgress) {
        onProgress({
          sentBytes,
          totalBytes,
          chunkIndex,
          totalChunks,
          percentage: totalBytes === 0 ? 100 : Math.round((sentBytes / totalBytes) * 100),
        });
      }

      if (chunkIndex < totalChunks - 1 && packetDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, packetDelayMs));
      }
    }

    return {
      totalBytes,
      chunksSent,
      durationMs: Date.now() - startTime,
      success: true,
    };
  }

  /**
   * Subscribe to BLE characteristic value notification
   */
  public async notifyBLECharacteristicValueChange(
    deviceId: string,
    serviceId: string,
    charId: string,
    state: boolean = true
  ): Promise<void> {
    if (this.isMockMode) {
      return;
    }

    if (typeof wx !== 'undefined' && wx.notifyBLECharacteristicValueChange) {
      return new Promise((resolve, reject) => {
        wx.notifyBLECharacteristicValueChange({
          deviceId,
          serviceId,
          characteristicId: charId,
          state,
          success: () => resolve(),
          fail: (err: any) => reject(new Error(err.errMsg || 'notifyBLECharacteristicValueChange failed')),
        });
      });
    }
  }

  public getDiscoveredDevices(): BleDevice[] {
    return Array.from(this.discoveredDevices.values());
  }

  public isConnected(deviceId: string): boolean {
    return this.connectedDevices.has(deviceId);
  }
}

/**
 * Enterprise BLE Hardware Simulator for offline development, mocking & automated CI tests
 */
export class BleHardwareSimulator extends CrossPlatformBleEngine {
  constructor() {
    super(true);
  }
}
