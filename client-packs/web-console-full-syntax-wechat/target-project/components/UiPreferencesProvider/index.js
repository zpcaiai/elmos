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
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          setLocaleState(storedLocale());
    setThemeState(storedTheme());
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_1
      (async () => {
        try {
          document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
        } catch (err) {
          // Handled mount effect
        }
      })();
    },
    detached() {
    },
  },
  methods: {
  },
});
