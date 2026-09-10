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
      try {
        setLocaleState(storedLocale());
    setThemeState(storedTheme());
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_1
      try {
        document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
  },
});
