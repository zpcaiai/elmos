Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    wallet: null,
    ledger: [],
    handoff: null,
    amountYuan: "",
    feedback: "",
    failure: "",
    busy: false,
    idempotencyKey: "",
    keyAmount: -1,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      try {
        if (account.status === "authenticated") void load();
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_1
      try {
        if (!handoff || handoff.status === "CREDITED" || handoff.status === "EXPIRED") return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(
          `/api/wallet/topup/${encodeURIComponent(handoff.topupOrderId)}`,
          { cache: "no-store", credentials: "same-origin" });
        if (!response.ok || cancelled) return;
        const order = await response.json().catch(() => null) as { status?: string } | null;
        if (!order?.status || cancelled) return;
        if (order.status !== handoff.status) {
          setHandoff((current) => current && { ...current, status: order.status as string });
        }
        if (order.status === "CREDITED") {
          idempotencyKey.current = "";
          keyAmount.current = -1;
          setFeedback("充值已入账。");
          await load();
        }
      } catch {
        // 轮询失败不打扰用户：下一轮会再试，真到不了会停在「已付款待入账」，
        // 那本身就是给运营看的信号。
      }
    }, 4000);
    return () => { cancelled = true; clearInterval(timer); };
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    submitTopup(event) {
      event.preventDefault();
    setFeedback("");
    setFailure("");
    const parsed = Number(amountYuan);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        setFailure("请输入大于零的充值金额。");
        return;
    }
    const amountMinor = Math.round(parsed * 100);
    if (amountMinor <= 0) {
        setFailure("请输入大于零的充值金额。");
        return;
    }
    if (keyAmount.current !== amountMinor || !idempotencyKey.current) {
        keyAmount.current = amountMinor;
        idempotencyKey.current = `topup-${crypto.randomUUID()}`;
    }
    setBusy(true);
    try {
        const response = await fetch("/api/wallet/topup", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotencyKey.current,
            },
            body: JSON.stringify({ amountMinor }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            // 键不作废：这一笔可能已经在服务端建好了，换键重试会开出第二笔可付款的单。
            setFailure(payload?.message ?? payload?.code ?? `充值未能发起（HTTP ${response.status}）。`);
            return;
        }
        setHandoff(payload);
        setFeedback(payload?.qrCodeUrl
            ? "已生成付款二维码，请用微信扫码完成付款。"
            : "已生成付款链接，请在新页面完成付款。");
    }
    catch {
        setFailure("充值请求结果未知，请不要重复提交——刷新后查看是否已有待付款订单。");
    }
    finally {
        setBusy(false);
    }
    },
  },
});
