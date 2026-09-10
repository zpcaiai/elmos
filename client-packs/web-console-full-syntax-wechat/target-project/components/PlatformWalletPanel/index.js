// Top-level helpers and constants
try { function yuan(minor) {
    if (minor === null || minor === undefined)
        return "—";
    const value = typeof minor === "number" ? minor : Number(minor);
    if (!Number.isFinite(value))
        return "—";
    return (value / 100).toLocaleString("zh-CN", {
        style: "currency",
        currency: "CNY",
        minimumFractionDigits: 2,
    });
} } catch(e) {}
try { function moment(value) {
    if (!value)
        return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("zh-CN", { hour12: false });
} } catch(e) {}
try { async function readRows(response) {
    const payload = (await response.json().catch(() => null));
    if (!response.ok) {
        return {
            rows: [],
            denial: payload?.code ?? payload?.message ?? `HTTP_${response.status}`,
        };
    }
    return { rows: payload?.rows ?? [], denial: "" };
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    canAdjust: {
      type: null,
      value: null,
    },
  },
  data: {
    wallets: [],
    topups: [],
    loaded: false,
    expanded: "",
    ledger: [],
    ledgerBusy: false,
    denial: "",
    notice: "",
    busy: false,
    target: "",
    amountYuan: "",
    direction: "CREDIT",
    reason: "",
    idempotencyKey: {"current":null},
    keySignature: {"current":null},
  },
  lifetimes: {
    attached() {
      const setWallets = (val) => { this.setData({ wallets: typeof val === "function" ? val(this.data.wallets) : val }); };
      const setTopups = (val) => { this.setData({ topups: typeof val === "function" ? val(this.data.topups) : val }); };
      const setLoaded = (val) => { this.setData({ loaded: typeof val === "function" ? val(this.data.loaded) : val }); };
      const setExpanded = (val) => { this.setData({ expanded: typeof val === "function" ? val(this.data.expanded) : val }); };
      const setLedger = (val) => { this.setData({ ledger: typeof val === "function" ? val(this.data.ledger) : val }); };
      const setLedgerBusy = (val) => { this.setData({ ledgerBusy: typeof val === "function" ? val(this.data.ledgerBusy) : val }); };
      const setDenial = (val) => { this.setData({ denial: typeof val === "function" ? val(this.data.denial) : val }); };
      const setNotice = (val) => { this.setData({ notice: typeof val === "function" ? val(this.data.notice) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setTarget = (val) => { this.setData({ target: typeof val === "function" ? val(this.data.target) : val }); };
      const setAmountYuan = (val) => { this.setData({ amountYuan: typeof val === "function" ? val(this.data.amountYuan) : val }); };
      const setDirection = (val) => { this.setData({ direction: typeof val === "function" ? val(this.data.direction) : val }); };
      const setReason = (val) => { this.setData({ reason: typeof val === "function" ? val(this.data.reason) : val }); };
      const idempotencyKey = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const keySignature = { current: { focus: () => {}, scrollIntoView: () => {} } };
    },
    detached() {
    },
  },
  methods: {
    async submitAdjustment(event) {
      const idempotencyKey = this.data.idempotencyKey || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const keySignature = this.data.keySignature || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event.preventDefault();
    setNotice("");
    const parsed = Number(amountYuan);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        setDenial("ADJUSTMENT_AMOUNT_INVALID");
        return;
    }
    const amountMinor = Math.round(parsed * 100);
    if (amountMinor <= 0) {
        setDenial("ADJUSTMENT_AMOUNT_INVALID");
        return;
    }
    const signature = `${target}|${direction}|${amountMinor}`;
    if (keySignature.current !== signature || !idempotencyKey.current) {
        keySignature.current = signature;
        idempotencyKey.current = `adj-${crypto.randomUUID()}`;
    }
    setBusy(true);
    setDenial("");
    try {
        const response = await fetch("/api/admin/wallets/adjust", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                organizationId: target,
                direction,
                amountMinor,
                reason: reason.trim(),
                idempotencyKey: idempotencyKey.current,
            }),
        });
        const payload = (await response.json().catch(() => null));
        if (!response.ok) {
            // 键刻意不作废：这一笔可能已经在服务端成立了，换键重试会入两次账。
            setDenial(payload?.code ?? payload?.message ?? `HTTP_${response.status}`);
            return;
        }
        idempotencyKey.current = "";
        keySignature.current = "";
        setAmountYuan("");
        setReason("");
        setNotice(`已入账，流水 ${payload?.entryId ?? "(未回传编号)"}。`);
        await load();
    }
    catch {
        // 未知结果：既不清键也不重试，由人决定。
        setDenial("ADJUSTMENT_RESULT_UNKNOWN");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("submitAdjustment execution warning:", err);
      }
    },
  },
});
