// Top-level helpers and constants
try { var localeKey = "elmos:ui-locale:v1"; } catch(e) {}
try { var themeKey = "elmos:ui-theme:v1"; } catch(e) {}
try { var storedLocale = function storedLocale() {
    try {
        return localStorage.getItem(localeKey) === "en" ? "en" : "zh-CN";
    }
    catch {
        return "zh-CN";
    }
} } catch(e) {}
try { var storedTheme = function storedTheme() {
    try {
        return localStorage.getItem(themeKey) === "dark" ? "dark" : "light";
    }
    catch {
        return "light";
    }
} } catch(e) {}
try { var useUiPreferences = function useUiPreferences() {
    const value = useContext(PreferencesContext);
    if (!value)
        throw new Error("UI_PREFERENCES_PROVIDER_MISSING");
    return value;
} } catch(e) {}

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
