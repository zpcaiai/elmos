/**
 * Bidirectional Event Normalization & Delegation Bridge.
 * 
 * Normalizes WeChat MiniProgram events (bindtap, catchtap, bindinput, bindchange, touch)
 * into W3C-compliant SyntheticEvent interfaces expected by React, Vue 3, and Angular handlers.
 */

export interface MiniAppRawEvent {
  type: string;
  timeStamp: number;
  target: {
    id: string;
    offsetLeft: number;
    offsetTop: number;
    dataset: Record<string, any>;
  };
  currentTarget: {
    id: string;
    offsetLeft: number;
    offsetTop: number;
    dataset: Record<string, any>;
  };
  detail?: any;
  touches?: Array<{
    identifier: number;
    pageX: number;
    pageY: number;
    clientX: number;
    clientY: number;
  }>;
  changedTouches?: Array<{
    identifier: number;
    pageX: number;
    pageY: number;
    clientX: number;
    clientY: number;
  }>;
}

export interface SyntheticWebEvent<T = any> {
  type: string;
  target: {
    id: string;
    value?: any;
    checked?: boolean;
    dataset: Record<string, any>;
  };
  currentTarget: {
    id: string;
    dataset: Record<string, any>;
  };
  clientX: number;
  clientY: number;
  pageX: number;
  pageY: number;
  bubbles: boolean;
  cancelable: boolean;
  defaultPrevented: boolean;
  isPropagationStopped: boolean;
  nativeEvent: MiniAppRawEvent;
  preventDefault(): void;
  stopPropagation(): void;
  stopImmediatePropagation(): void;
  persist?(): void;
}

export class EventNormalizationBridge {
  /**
   * Transforms a native WeChat event into a W3C-compatible SyntheticWebEvent.
   */
  public static normalize(rawEvent: MiniAppRawEvent): SyntheticWebEvent {
    let defaultPrevented = false;
    let isPropagationStopped = false;

    // 1. Extract coordinates
    let clientX = 0;
    let clientY = 0;
    let pageX = 0;
    let pageY = 0;

    if (rawEvent.touches && rawEvent.touches.length > 0) {
      const touch = rawEvent.touches[0]!;
      clientX = touch.clientX;
      clientY = touch.clientY;
      pageX = touch.pageX;
      pageY = touch.pageY;
    } else if (rawEvent.changedTouches && rawEvent.changedTouches.length > 0) {
      const touch = rawEvent.changedTouches[0]!;
      clientX = touch.clientX;
      clientY = touch.clientY;
      pageX = touch.pageX;
      pageY = touch.pageY;
    } else if (rawEvent.detail && typeof rawEvent.detail.x === "number") {
      clientX = rawEvent.detail.x;
      clientY = rawEvent.detail.y;
      pageX = rawEvent.detail.x;
      pageY = rawEvent.detail.y;
    }

    // 2. Extract value & checked for form events
    let targetValue: any = undefined;
    let targetChecked: boolean | undefined = undefined;

    if (rawEvent.detail !== undefined) {
      if (typeof rawEvent.detail === "object" && rawEvent.detail !== null) {
        if ("value" in rawEvent.detail) {
          targetValue = rawEvent.detail.value;
          if (typeof rawEvent.detail.value === "boolean") {
            targetChecked = rawEvent.detail.value;
          }
        }
      } else {
        targetValue = rawEvent.detail;
      }
    }

    // Map MiniApp event types to standard Web event types
    const mappedType = this.mapEventType(rawEvent.type);

    const synthetic: SyntheticWebEvent = {
      type: mappedType,
      target: {
        id: rawEvent.target ? rawEvent.target.id : "",
        value: targetValue,
        checked: targetChecked,
        dataset: rawEvent.target ? rawEvent.target.dataset : {},
      },
      currentTarget: {
        id: rawEvent.currentTarget ? rawEvent.currentTarget.id : "",
        dataset: rawEvent.currentTarget ? rawEvent.currentTarget.dataset : {},
      },
      clientX,
      clientY,
      pageX,
      pageY,
      bubbles: true,
      cancelable: true,
      get defaultPrevented() {
        return defaultPrevented;
      },
      get isPropagationStopped() {
        return isPropagationStopped;
      },
      nativeEvent: rawEvent,
      preventDefault() {
        defaultPrevented = true;
      },
      stopPropagation() {
        isPropagationStopped = true;
      },
      stopImmediatePropagation() {
        isPropagationStopped = true;
      },
      persist() {},
    };

    return synthetic;
  }

  /**
   * Adapts a standard Web event handler to be executed by a WeChat MiniApp method.
   */
  public static wrapHandler<T = any>(
    handler: (e: SyntheticWebEvent<T>, ...args: any[]) => void
  ): (rawEvent: MiniAppRawEvent) => void {
    return (rawEvent: MiniAppRawEvent) => {
      const synthetic = EventNormalizationBridge.normalize(rawEvent);
      handler(synthetic);
    };
  }

  private static mapEventType(wxType: string): string {
    switch (wxType) {
      case "tap":
        return "click";
      case "input":
        return "input";
      case "change":
        return "change";
      case "blur":
        return "blur";
      case "focus":
        return "focus";
      case "submit":
        return "submit";
      case "touchstart":
        return "touchstart";
      case "touchmove":
        return "touchmove";
      case "touchend":
        return "touchend";
      case "touchcancel":
        return "touchcancel";
      default:
        return wxType;
    }
  }
}
