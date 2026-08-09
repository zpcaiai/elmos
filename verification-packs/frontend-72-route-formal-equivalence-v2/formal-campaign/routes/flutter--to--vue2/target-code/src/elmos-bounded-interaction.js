// Generated sole executable semantic contract for bounded-frontend-interaction-v1.
export const ELMOS_FRONTEND_INTERACTION = {
  "schemaVersion": "1.0",
  "profile": "bounded-frontend-interaction-v1",
  "projectTitle": "ELMOS 有界前端交互验证",
  "navigation": {
    "label": "主要导航",
    "fallback": "FIRST_DECLARED_ROUTE",
    "routes": [
      {
        "id": "route.home",
        "path": "/",
        "title": "首页",
        "text": "首页内容",
        "requiresAuth": false,
        "deepLink": true
      },
      {
        "id": "route.account",
        "path": "/account",
        "title": "账户",
        "text": "账户内容",
        "requiresAuth": true,
        "deepLink": true
      },
      {
        "id": "route.help",
        "path": "/help",
        "title": "帮助",
        "text": "帮助内容",
        "requiresAuth": false,
        "deepLink": false
      }
    ]
  },
  "componentTemplate": {
    "componentId": "interaction.shell",
    "templateKind": "ROUTE_DETAIL_WITH_INTERACTION_MATRIX",
    "keyedBy": "route.id",
    "titleBinding": "route.title",
    "textBinding": "route.text"
  },
  "stateManagement": {
    "stateId": "bounded.counter",
    "initial": 0,
    "minimum": 0,
    "maximum": 2,
    "transition": "SATURATING_INCREMENT"
  },
  "actionEvent": {
    "acceptedEvents": [
      "BOOT",
      "NAVIGATE",
      "AUTHENTICATE",
      "SUBMIT",
      "CANCEL",
      "HYDRATE",
      "DISPLAY_CHANGE",
      "NATIVE_DEEPLINK"
    ],
    "deniedAction": "BLOCK",
    "keyboardSubmit": "Enter"
  },
  "effectLifecycle": {
    "mountEffect": "LOAD_ON_MOUNT",
    "cleanupEffect": "CANCEL_ON_UNMOUNT",
    "maxExecutionsPerMount": 1,
    "staleResponsePolicy": "IGNORE_AFTER_CANCEL"
  },
  "formBindingValidation": {
    "formId": "search",
    "fieldId": "query",
    "initialValue": "",
    "required": true,
    "minimumLength": 2,
    "validation": "ON_SUBMIT",
    "invalidCode": "QUERY_TOO_SHORT"
  },
  "apiNetwork": {
    "operationId": "search",
    "method": "POST",
    "path": "/api/search",
    "timeoutMs": 1000,
    "retry": "NEVER",
    "cacheScope": "TENANT_QUERY",
    "cancelOnUnmount": true
  },
  "identityPermission": {
    "anonymousRole": "ANONYMOUS",
    "authenticatedRole": "MEMBER",
    "requiredPermission": "search:execute",
    "deniedBehavior": "HIDE_AND_BLOCK",
    "tenantIsolation": "EXACT_TENANT_MATCH",
    "serverAuthorityRequired": true
  },
  "renderingHydration": {
    "mode": "HYDRATABLE_CSR",
    "hydrationPolicy": "REQUIRE_MATCH",
    "mismatchBehavior": "RENDER_ERROR",
    "duplicateEffectsAllowed": false
  },
  "accessibilityFocus": {
    "mainRole": "main",
    "headingLevel": 1,
    "formLabel": "搜索",
    "errorRole": "alert",
    "liveRegion": "polite",
    "invalidFocusTarget": "query",
    "keyboardSubmit": "Enter"
  },
  "i18nThemeResponsive": {
    "supportedLocales": [
      "zh-CN",
      "en-US"
    ],
    "fallbackLocale": "en-US",
    "themes": [
      "LIGHT",
      "DARK"
    ],
    "defaultTheme": "LIGHT",
    "compactBreakpoint": 720,
    "compactColumns": 1,
    "wideColumns": 2
  },
  "nativePlatform": {
    "boundary": "ADAPTER",
    "capability": "OPEN_DEEP_LINK",
    "lifecycleStates": [
      "FOREGROUND",
      "BACKGROUND"
    ],
    "permission": "DEEPLINK_OPEN",
    "deniedBehavior": "NO_OP_REPORTED",
    "recovery": "FOREGROUND_RETRY"
  }
};
export const ELMOS_INTERACTION_ROUTES = ELMOS_FRONTEND_INTERACTION.navigation.routes;
export const ELMOS_INTERACTION_SCENARIOS = [
  {
    "scenarioId": "BOOT_PUBLIC",
    "input": {
      "routePath": "/",
      "event": "BOOT",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "MOUNT",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "MATCH",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "NAVIGATE_PROTECTED_ANONYMOUS_DENIED",
    "input": {
      "routePath": "/account",
      "event": "NAVIGATE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "AUTHENTICATE_AND_NAVIGATE_PROTECTED",
    "input": {
      "routePath": "/account",
      "event": "AUTHENTICATE",
      "counterBefore": 0,
      "incrementCount": 1,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "FORM_INVALID_SUBMIT_FOCUS_ERROR",
    "input": {
      "routePath": "/account",
      "event": "SUBMIT",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "x",
      "keyboardKey": "Enter",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "FORM_VALID_SUBMIT_API_SUCCESS",
    "input": {
      "routePath": "/account",
      "event": "SUBMIT",
      "counterBefore": 0,
      "incrementCount": 3,
      "lifecycle": "ACTIVE",
      "query": "ok",
      "keyboardKey": "Enter",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "SUCCESS",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "API_ERROR_CANCEL_STALE_RESPONSE",
    "input": {
      "routePath": "/account",
      "event": "CANCEL",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "UNMOUNT",
      "query": "fail",
      "keyboardKey": "NONE",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "STALE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "HYDRATE_MATCH_SINGLE_EFFECT_CLEANUP",
    "input": {
      "routePath": "/",
      "event": "HYDRATE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "UNMOUNT",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "MATCH",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "LOCALE_THEME_VIEWPORT_CHANGE",
    "input": {
      "routePath": "/",
      "event": "DISPLAY_CHANGE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "fr-FR",
      "theme": "DARK",
      "viewportWidth": 480,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "NATIVE_DEEPLINK_BACKGROUND_PERMISSION_DENIED_RECOVERY",
    "input": {
      "routePath": "/",
      "event": "NATIVE_DEEPLINK",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "BACKGROUND",
      "deepLinkPath": "/account",
      "nativePermission": "DENIED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "TENANT_ISOLATION_MISMATCH_DENIED",
    "input": {
      "routePath": "/account",
      "event": "SUBMIT",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "ok",
      "keyboardKey": "NONE",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-b",
      "networkResult": "SUCCESS",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "API_NETWORK_ERROR",
    "input": {
      "routePath": "/account",
      "event": "SUBMIT",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "ok",
      "keyboardKey": "NONE",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "ERROR",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "HYDRATE_MISMATCH_ERROR",
    "input": {
      "routePath": "/",
      "event": "HYDRATE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "MOUNT",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "MISMATCH",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN",
    "input": {
      "routePath": "/",
      "event": "NATIVE_DEEPLINK",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": "/account",
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "LOCALE_EN_US_WIDE_721",
    "input": {
      "routePath": "/",
      "event": "DISPLAY_CHANGE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "en-US",
      "theme": "LIGHT",
      "viewportWidth": 721,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "UNSUPPORTED_THEME_FALLBACK",
    "input": {
      "routePath": "/",
      "event": "DISPLAY_CHANGE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "SEPIA",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "BREAKPOINT_720_COMPACT",
    "input": {
      "routePath": "/",
      "event": "DISPLAY_CHANGE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 720,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "NAVIGATE_HELP_PUBLIC",
    "input": {
      "routePath": "/help",
      "event": "NAVIGATE",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "",
      "keyboardKey": "NONE",
      "authenticated": false,
      "permissionGranted": false,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "NONE",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  },
  {
    "scenarioId": "KEYBOARD_ENTER_SUBMIT",
    "input": {
      "routePath": "/account",
      "event": "BOOT",
      "counterBefore": 0,
      "incrementCount": 0,
      "lifecycle": "ACTIVE",
      "query": "ok",
      "keyboardKey": "Enter",
      "authenticated": true,
      "permissionGranted": true,
      "tenantId": "tenant-a",
      "resourceTenantId": "tenant-a",
      "networkResult": "SUCCESS",
      "hydration": "NONE",
      "locale": "zh-CN",
      "theme": "LIGHT",
      "viewportWidth": 1024,
      "nativeLifecycle": "FOREGROUND",
      "deepLinkPath": null,
      "nativePermission": "GRANTED",
      "nativeAvailable": true
    }
  }
];

const ELMOS_INTERACTION_REDUCER = function observeBoundedFrontendInteraction(model, scenarioValue) {
    const input = scenarioValue.input;
    const first = model.navigation.routes[0];
    if (!first)
        throw new Error("bounded interaction observation requires a route");
    const requested = model.navigation.routes.find(route => route.path === input.routePath)
        ?? (model.navigation.fallback === "FIRST_DECLARED_ROUTE" ? first : first);
    const tenantMatch = model.identityPermission.tenantIsolation === "EXACT_TENANT_MATCH"
        ? input.tenantId === input.resourceTenantId : false;
    const authorized = !requested.requiresAuth || (input.authenticated && input.permissionGranted && tenantMatch);
    const selected = authorized ? requested : first;
    const boundQuery = input.query.length === 0 ? model.formBindingValidation.initialValue : input.query;
    const valid = (!model.formBindingValidation.required || boundQuery.length > 0)
        && boundQuery.length >= model.formBindingValidation.minimumLength;
    const submitted = input.event === "SUBMIT" || input.keyboardKey === model.actionEvent.keyboardSubmit;
    const validated = model.formBindingValidation.validation === "ON_SUBMIT" ? submitted : true;
    const apiCalled = validated && valid && authorized;
    const canceled = input.event === "CANCEL" || (model.apiNetwork.cancelOnUnmount && input.lifecycle === "UNMOUNT");
    const staleIgnored = input.networkResult === "STALE" && canceled
        && model.effectLifecycle.staleResponsePolicy === "IGNORE_AFTER_CANCEL";
    const effectExecutions = input.lifecycle === "MOUNT" ? model.effectLifecycle.maxExecutionsPerMount : 0;
    const counterBase = Math.max(model.stateManagement.initial, input.counterBefore);
    const counterAfter = model.stateManagement.transition === "SATURATING_INCREMENT"
        ? Math.min(model.stateManagement.maximum, Math.max(model.stateManagement.minimum, counterBase + input.incrementCount))
        : counterBase;
    const hydrationStatus = input.hydration === "MISMATCH" && model.renderingHydration.hydrationPolicy === "REQUIRE_MATCH"
        ? model.renderingHydration.mismatchBehavior : input.hydration === "MATCH" ? "MATCHED" : "NOT_ATTEMPTED";
    const locale = model.i18nThemeResponsive.supportedLocales.some(value => value === input.locale)
        ? input.locale : model.i18nThemeResponsive.fallbackLocale;
    const theme = model.i18nThemeResponsive.themes.some(value => value === input.theme)
        ? input.theme : model.i18nThemeResponsive.defaultTheme;
    const nativeTarget = input.deepLinkPath === null ? null : model.navigation.routes.find(route => route.path === input.deepLinkPath) ?? first;
    const nativeTargetAuthorized = nativeTarget === null || !nativeTarget.requiresAuth
        || (input.authenticated && input.permissionGranted && tenantMatch);
    const nativeAttempted = input.event === "NATIVE_DEEPLINK" && input.deepLinkPath !== null
        && model.nativePlatform.capability === "OPEN_DEEP_LINK";
    const nativeLifecycleKnown = model.nativePlatform.lifecycleStates.includes(input.nativeLifecycle);
    const nativeAllowed = nativeAttempted && input.nativeAvailable && input.nativePermission === "GRANTED"
        && input.nativeLifecycle === "FOREGROUND" && nativeLifecycleKnown && nativeTargetAuthorized;
    const networkOutcome = !apiCalled ? "NOT_CALLED" : canceled ? "CANCELED"
        : input.networkResult === "SUCCESS" ? "SUCCESS" : input.networkResult === "ERROR" ? "ERROR" : "PENDING";
    const formError = validated && !valid ? model.formBindingValidation.invalidCode : null;
    const focusTarget = formError === null ? (submitted ? "result" : null) : model.accessibilityFocus.invalidFocusTarget;
    const resolution = requested === first && input.routePath !== first.path ? "FIRST_DECLARED_FALLBACK"
        : authorized ? "DECLARED" : "AUTH_DENIED_FALLBACK";
    return {
        scenarioId: scenarioValue.scenarioId,
        before: { counter: input.counterBefore, lifecycle: input.lifecycle, query: input.query, authenticated: input.authenticated },
        after: { counter: counterAfter, selectedRouteId: selected.id, authorized, apiCalled, focusTarget, nativeAllowed },
        blocks: {
            "route-navigation-deeplink-404": {
                requestedPath: input.routePath, selectedRouteId: selected.id, selectedPath: selected.path,
                resolution, navigationLabel: model.navigation.label, fallback: model.navigation.fallback,
                deepLink: selected.deepLink, requiresAuth: selected.requiresAuth,
            },
            "component-template-view": {
                componentId: model.componentTemplate.componentId, templateKind: model.componentTemplate.templateKind,
                keyedBy: model.componentTemplate.keyedBy, titleBinding: model.componentTemplate.titleBinding,
                textBinding: model.componentTemplate.textBinding,
                key: model.componentTemplate.keyedBy === "route.id" ? selected.id : "",
                title: model.componentTemplate.titleBinding === "route.title" ? selected.title : "",
                text: model.componentTemplate.textBinding === "route.text" ? selected.text : "", visible: true,
            },
            "state-management": {
                stateId: model.stateManagement.stateId, initial: model.stateManagement.initial, minimum: model.stateManagement.minimum,
                maximum: model.stateManagement.maximum, transition: model.stateManagement.transition,
                before: input.counterBefore, after: counterAfter, saturated: counterBase + input.incrementCount > model.stateManagement.maximum,
            },
            "action-event": {
                event: input.event, keyboardKey: input.keyboardKey, handled: model.actionEvent.acceptedEvents.includes(input.event),
                action: submitted ? (valid && authorized ? "SUBMIT_ACCEPTED" : model.actionEvent.deniedAction) : input.event,
            },
            "effect-lifecycle": {
                lifecycle: input.lifecycle, mountEffect: input.lifecycle === "MOUNT" ? model.effectLifecycle.mountEffect : "NONE",
                cleanupEffect: input.lifecycle === "UNMOUNT" ? model.effectLifecycle.cleanupEffect : "NONE",
                maxExecutionsPerMount: model.effectLifecycle.maxExecutionsPerMount,
                staleResponsePolicy: model.effectLifecycle.staleResponsePolicy,
                executions: effectExecutions, cleanup: input.lifecycle === "UNMOUNT", staleResponseIgnored: staleIgnored,
            },
            "form-binding-validation": {
                formId: model.formBindingValidation.formId, fieldId: model.formBindingValidation.fieldId,
                initialValue: model.formBindingValidation.initialValue, required: model.formBindingValidation.required,
                minimumLength: model.formBindingValidation.minimumLength, validation: model.formBindingValidation.validation,
                value: boundQuery, submitted, validated, valid, errorCode: formError,
            },
            "api-network": {
                operationId: model.apiNetwork.operationId, called: apiCalled, method: model.apiNetwork.method,
                path: model.apiNetwork.path, timeoutMs: model.apiNetwork.timeoutMs, retry: model.apiNetwork.retry,
                cacheScope: model.apiNetwork.cacheScope, cancelOnUnmount: model.apiNetwork.cancelOnUnmount,
                outcome: networkOutcome, canceled, staleIgnored,
                cacheKey: model.apiNetwork.cacheScope === "TENANT_QUERY" ? `${input.tenantId}:${boundQuery}` : boundQuery,
            },
            "identity-permission": {
                role: input.authenticated ? model.identityPermission.authenticatedRole : model.identityPermission.anonymousRole,
                permission: model.identityPermission.requiredPermission, permissionGranted: input.permissionGranted,
                deniedBehavior: model.identityPermission.deniedBehavior, tenantIsolation: model.identityPermission.tenantIsolation,
                tenantMatch, authorized, serverAuthorityRequired: model.identityPermission.serverAuthorityRequired,
            },
            "rendering-hydration": {
                mode: model.renderingHydration.mode, hydrationPolicy: model.renderingHydration.hydrationPolicy,
                requested: input.hydration, status: hydrationStatus,
                duplicateEffectsAllowed: model.renderingHydration.duplicateEffectsAllowed,
                duplicateEffects: model.renderingHydration.duplicateEffectsAllowed && input.hydration === "MISMATCH",
                mismatchVisible: input.hydration === "MISMATCH",
            },
            "accessibility-focus": {
                mainRole: model.accessibilityFocus.mainRole, headingLevel: model.accessibilityFocus.headingLevel,
                formLabel: model.accessibilityFocus.formLabel, errorRole: formError === null ? null : model.accessibilityFocus.errorRole,
                liveRegion: model.accessibilityFocus.liveRegion, keyboardSubmit: input.keyboardKey === model.accessibilityFocus.keyboardSubmit,
                focusTarget,
            },
            "i18n-theme-responsive": {
                requestedLocale: input.locale, localeSupported: model.i18nThemeResponsive.supportedLocales.some(value => value === input.locale), locale,
                requestedTheme: input.theme, themeSupported: model.i18nThemeResponsive.themes.some(value => value === input.theme), theme,
                viewportWidth: input.viewportWidth,
                columns: input.viewportWidth <= model.i18nThemeResponsive.compactBreakpoint
                    ? model.i18nThemeResponsive.compactColumns : model.i18nThemeResponsive.wideColumns,
            },
            "native-platform": {
                boundary: model.nativePlatform.boundary, capability: model.nativePlatform.capability,
                lifecycleStates: model.nativePlatform.lifecycleStates.join("|"), lifecycle: input.nativeLifecycle,
                lifecycleKnown: nativeLifecycleKnown, deepLinkPath: input.deepLinkPath,
                targetRouteId: nativeTarget?.id ?? null, targetAuthorized: nativeTargetAuthorized, attempted: nativeAttempted,
                permissionContract: model.nativePlatform.permission, permission: input.nativePermission, available: input.nativeAvailable,
                deniedBehavior: model.nativePlatform.deniedBehavior,
                outcome: !nativeAttempted ? "NOT_ATTEMPTED" : nativeAllowed ? "OPENED" : model.nativePlatform.deniedBehavior,
                recovery: nativeAllowed ? "NOT_REQUIRED" : model.nativePlatform.recovery,
            },
        },
    };
};
export function elmosObserveInteraction(scenario) { return ELMOS_INTERACTION_REDUCER(ELMOS_FRONTEND_INTERACTION, scenario); }
