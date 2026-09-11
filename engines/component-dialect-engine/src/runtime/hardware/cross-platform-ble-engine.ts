/**
 * @file cross-platform-ble-engine.ts
 * @description Enterprise Cross-Platform Bluetooth Low Energy (BLE 4.0/5.0) Engine.
 * Provides unified bidirectional abstraction across WeChat MiniApp BLE APIs
 * and Web Bluetooth API (navigator.bluetooth), with offline mock simulation.
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

export interface BleEventMap {
  onDeviceFound: (device: BleDevice) => void;
  onConnectionStateChange: (deviceId: string, connected: boolean) => void;
  onCharacteristicValueChange: (deviceId: string, serviceId: string, charId: string, value: ArrayBuffer) => void;
}

export class CrossPlatformBleEngine {
  private isMockMode: boolean;
  private isAdapterOpened = false;
  private discoveredDevices: Map<string, BleDevice> = new Map();
  private connectedDevices: Set<string> = new Set();
  private listeners: Partial<BleEventMap> = {};
  private mockServices: Map<string, BleService[]> = new Map();
  private mockCharacteristics: Map<string, BleCharacteristic[]> = new Map();

  constructor(mockMode: boolean = false) {
    this.isMockMode = mockMode || typeof wx === 'undefined' && typeof navigator === 'undefined';
  }

  public setEventListeners(listeners: Partial<BleEventMap>): void {
    this.listeners = { ...this.listeners, ...listeners };
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

  /**
   * Close Bluetooth Adapter
   */
  public async closeAdapter(): Promise<void> {
    this.isAdapterOpened = false;
    this.connectedDevices.clear();
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
      // Simulate finding a mock device
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
   * Connect to a BLE peripheral
   */
  public async connect(deviceId: string): Promise<void> {
    if (this.isMockMode) {
      this.connectedDevices.add(deviceId);
      // Register mock services
      this.mockServices.set(deviceId, [
        { uuid: '0000ffe0-0000-1000-8000-00805f9b34fb', isPrimary: true },
      ]);
      this.mockCharacteristics.set('0000ffe0-0000-1000-8000-00805f9b34fb', [
        {
          uuid: '0000ffe1-0000-1000-8000-00805f9b34fb',
          properties: { read: true, write: true, notify: true, indicate: false },
        },
      ]);
      if (this.listeners.onConnectionStateChange) {
        this.listeners.onConnectionStateChange(deviceId, true);
      }
      return;
    }

    if (typeof wx !== 'undefined' && wx.createBLEConnection) {
      return new Promise((resolve, reject) => {
        wx.createBLEConnection({
          deviceId,
          success: () => {
            this.connectedDevices.add(deviceId);
            if (this.listeners.onConnectionStateChange) {
              this.listeners.onConnectionStateChange(deviceId, true);
            }
            resolve();
          },
          fail: (err: any) => reject(new Error(err.errMsg || 'createBLEConnection failed')),
        });
      });
    }
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
   * Write data to a BLE characteristic
   */
  public async writeValue(
    deviceId: string,
    serviceId: string,
    charId: string,
    value: ArrayBuffer
  ): Promise<void> {
    if (this.isMockMode) {
      // Simulate successful write and echo back notification
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

  public getDiscoveredDevices(): BleDevice[] {
    return Array.from(this.discoveredDevices.values());
  }

  public isConnected(deviceId: string): boolean {
    return this.connectedDevices.has(deviceId);
  }
}
