Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    children: {
      type: null,
      value: null,
    },
  },
  data: {
    locale: "zh-CN",
    theme: "light",
    value: null,
  },
  lifetimes: {
    attached() {
      const setLocaleState = (val) => { this.setData({ locale: typeof val === "function" ? val(this.data.locale) : val }); };
      const setThemeState = (val) => { this.setData({ theme: typeof val === "function" ? val(this.data.theme) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          setLocaleState(storedLocale());
    setThemeState(storedTheme());
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
  },
});
