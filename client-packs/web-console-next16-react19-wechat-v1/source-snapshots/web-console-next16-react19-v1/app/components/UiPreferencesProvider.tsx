"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type UiLocale = "zh-CN" | "en";
export type UiTheme = "light" | "dark";

type UiPreferences = {
  locale: UiLocale;
  theme: UiTheme;
  setLocale: (locale: UiLocale) => void;
  setTheme: (theme: UiTheme) => void;
};

const PreferencesContext = createContext<UiPreferences | null>(null);
const localeKey = "elmos:ui-locale:v1";
const themeKey = "elmos:ui-theme:v1";

function storedLocale(): UiLocale {
  try {
    return localStorage.getItem(localeKey) === "en" ? "en" : "zh-CN";
  } catch {
    return "zh-CN";
  }
}

function storedTheme(): UiTheme {
  try {
    return localStorage.getItem(themeKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function UiPreferencesProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<UiLocale>("zh-CN");
  const [theme, setThemeState] = useState<UiTheme>("light");

  useEffect(() => {
    setLocaleState(storedLocale());
    setThemeState(storedTheme());
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [locale, theme]);

  const value = useMemo<UiPreferences>(() => ({
    locale,
    theme,
    setLocale(next) {
      setLocaleState(next);
      try {
        localStorage.setItem(localeKey, next);
      } catch {
        // Storage can be disabled; the in-memory preference remains valid.
      }
    },
    setTheme(next) {
      setThemeState(next);
      try {
        localStorage.setItem(themeKey, next);
      } catch {
        // Storage can be disabled; the in-memory preference remains valid.
      }
    },
  }), [locale, theme]);

  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function useUiPreferences(): UiPreferences {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("UI_PREFERENCES_PROVIDER_MISSING");
  return value;
}
