import { Buffer } from "node:buffer";
export const interactionBlockIds = [
    "route-navigation-deeplink-404",
    "component-template-view",
    "state-management",
    "action-event",
    "effect-lifecycle",
    "form-binding-validation",
    "api-network",
    "identity-permission",
    "rendering-hydration",
    "accessibility-focus",
    "i18n-theme-responsive",
    "native-platform",
];
export const interactionBlockSymbolMap = {
    "route-navigation-deeplink-404": "navigation",
    "component-template-view": "component_template",
    "state-management": "state_management",
    "action-event": "action_event",
    "effect-lifecycle": "effect_lifecycle",
    "form-binding-validation": "form_binding_validation",
    "api-network": "api_network",
    "identity-permission": "identity_permission",
    "rendering-hydration": "rendering_hydration",
    "accessibility-focus": "accessibility_focus",
    "i18n-theme-responsive": "i18n_theme_responsive",
    "native-platform": "native_platform",
};
export const interactionInfluenceMatrix = {
    "route-navigation-deeplink-404": {
        "/navigation/fallback": "TRANSITION", "/navigation/routes": "TRANSITION", "/navigation/label": "DECLARATION_ECHO",
    },
    "component-template-view": {
        "/componentTemplate/keyedBy": "TRANSITION", "/componentTemplate/titleBinding": "TRANSITION",
        "/componentTemplate/textBinding": "TRANSITION", "/componentTemplate/componentId": "DECLARATION_ECHO",
        "/componentTemplate/templateKind": "DECLARATION_ECHO",
    },
    "state-management": {
        "/stateManagement/initial": "TRANSITION", "/stateManagement/minimum": "TRANSITION",
        "/stateManagement/maximum": "TRANSITION", "/stateManagement/transition": "TRANSITION",
        "/stateManagement/stateId": "DECLARATION_ECHO",
    },
    "action-event": {
        "/actionEvent/acceptedEvents": "TRANSITION", "/actionEvent/deniedAction": "TRANSITION",
        "/actionEvent/keyboardSubmit": "TRANSITION",
    },
    "effect-lifecycle": {
        "/effectLifecycle/mountEffect": "OBSERVABLE_EFFECT", "/effectLifecycle/cleanupEffect": "OBSERVABLE_EFFECT",
        "/effectLifecycle/maxExecutionsPerMount": "TRANSITION", "/effectLifecycle/staleResponsePolicy": "TRANSITION",
    },
    "form-binding-validation": {
        "/formBindingValidation/initialValue": "TRANSITION", "/formBindingValidation/required": "TRANSITION",
        "/formBindingValidation/minimumLength": "TRANSITION", "/formBindingValidation/validation": "TRANSITION",
        "/formBindingValidation/invalidCode": "TRANSITION", "/formBindingValidation/formId": "DECLARATION_ECHO",
        "/formBindingValidation/fieldId": "DECLARATION_ECHO",
    },
    "api-network": {
        "/apiNetwork/method": "OBSERVABLE_EFFECT", "/apiNetwork/path": "OBSERVABLE_EFFECT",
        "/apiNetwork/timeoutMs": "OBSERVABLE_EFFECT", "/apiNetwork/retry": "TRANSITION",
        "/apiNetwork/cacheScope": "TRANSITION", "/apiNetwork/cancelOnUnmount": "TRANSITION",
        "/apiNetwork/operationId": "DECLARATION_ECHO",
    },
    "identity-permission": {
        "/identityPermission/anonymousRole": "TRANSITION", "/identityPermission/authenticatedRole": "TRANSITION",
        "/identityPermission/requiredPermission": "TRANSITION", "/identityPermission/deniedBehavior": "TRANSITION",
        "/identityPermission/tenantIsolation": "TRANSITION", "/identityPermission/serverAuthorityRequired": "OBSERVABLE_EFFECT",
    },
    "rendering-hydration": {
        "/renderingHydration/mode": "DECLARATION_ECHO", "/renderingHydration/hydrationPolicy": "TRANSITION",
        "/renderingHydration/mismatchBehavior": "TRANSITION", "/renderingHydration/duplicateEffectsAllowed": "TRANSITION",
    },
    "accessibility-focus": {
        "/accessibilityFocus/mainRole": "OBSERVABLE_EFFECT", "/accessibilityFocus/headingLevel": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/formLabel": "OBSERVABLE_EFFECT", "/accessibilityFocus/errorRole": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/liveRegion": "OBSERVABLE_EFFECT", "/accessibilityFocus/invalidFocusTarget": "TRANSITION",
        "/accessibilityFocus/keyboardSubmit": "TRANSITION",
    },
    "i18n-theme-responsive": {
        "/i18nThemeResponsive/supportedLocales": "TRANSITION", "/i18nThemeResponsive/fallbackLocale": "TRANSITION",
        "/i18nThemeResponsive/themes": "TRANSITION", "/i18nThemeResponsive/defaultTheme": "TRANSITION",
        "/i18nThemeResponsive/compactBreakpoint": "TRANSITION", "/i18nThemeResponsive/compactColumns": "TRANSITION",
        "/i18nThemeResponsive/wideColumns": "TRANSITION",
    },
    "native-platform": {
        "/nativePlatform/boundary": "DECLARATION_ECHO", "/nativePlatform/capability": "TRANSITION",
        "/nativePlatform/lifecycleStates": "TRANSITION", "/nativePlatform/permission": "OBSERVABLE_EFFECT",
        "/nativePlatform/deniedBehavior": "TRANSITION", "/nativePlatform/recovery": "TRANSITION",
    },
};
export const interactionRuntimeInfluenceMatrix = Object.fromEntries(interactionBlockIds.map(blockId => [blockId, Object.fromEntries(Object.entries(interactionInfluenceMatrix[blockId]).map(([pointer, influence]) => {
        const frameworkObservable = blockId === "route-navigation-deeplink-404" && pointer === "/navigation/routes";
        const adapter = influence === "OBSERVABLE_EFFECT" || blockId === "api-network" || blockId === "native-platform";
        return [pointer, frameworkObservable ? "FRAMEWORK_OBSERVABLE" : influence === "DECLARATION_ECHO" ? "DECLARATION_ECHO" : adapter ? "ADAPTER_SEAM_NOT_RUN" : "MODEL_ONLY_NOT_RUNTIME"];
    }))]));
export function aggregateModelInfluence(blockId) {
    const values = Object.values(interactionInfluenceMatrix[blockId]);
    if (values.includes("OBSERVABLE_EFFECT"))
        return "OBSERVABLE_EFFECT";
    if (values.includes("TRANSITION"))
        return "TRANSITION";
    return "DECLARATION_ECHO";
}
export function aggregateRuntimeInfluence(blockId) {
    const runtimeValues = Object.entries(interactionRuntimeInfluenceMatrix[blockId])
        .filter(([pointer]) => interactionInfluenceMatrix[blockId][pointer] !== "DECLARATION_ECHO")
        .map(([, value]) => value);
    if (runtimeValues.length === 0)
        return "DECLARATION_ECHO";
    if (runtimeValues.includes("MODEL_ONLY_NOT_RUNTIME"))
        return "MODEL_ONLY_NOT_RUNTIME";
    if (runtimeValues.includes("ADAPTER_SEAM_NOT_RUN"))
        return "ADAPTER_SEAM_NOT_RUN";
    return "FRAMEWORK_OBSERVABLE";
}
export const interactionScenarioIds = [
    "BOOT_PUBLIC",
    "NAVIGATE_PROTECTED_ANONYMOUS_DENIED",
    "AUTHENTICATE_AND_NAVIGATE_PROTECTED",
    "FORM_INVALID_SUBMIT_FOCUS_ERROR",
    "FORM_VALID_SUBMIT_API_SUCCESS",
    "API_ERROR_CANCEL_STALE_RESPONSE",
    "HYDRATE_MATCH_SINGLE_EFFECT_CLEANUP",
    "LOCALE_THEME_VIEWPORT_CHANGE",
    "NATIVE_DEEPLINK_BACKGROUND_PERMISSION_DENIED_RECOVERY",
    "TENANT_ISOLATION_MISMATCH_DENIED",
    "API_NETWORK_ERROR",
    "HYDRATE_MISMATCH_ERROR",
    "NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN",
    "LOCALE_EN_US_WIDE_721",
    "UNSUPPORTED_THEME_FALLBACK",
    "BREAKPOINT_720_COMPACT",
    "NAVIGATE_HELP_PUBLIC",
    "KEYBOARD_ENTER_SUBMIT",
];
export function interactionSourceSpec(profile) {
    switch (profile) {
        case "vue2":
            return { sourcePath: "src/elmos-bounded-interaction.js", compatibilityPath: "src/elmos-bounded-navigation.js", parser: "TYPESCRIPT_AST" };
        case "react-native":
            return { sourcePath: "src/elmos-bounded-interaction.ts", compatibilityPath: "src/elmos-bounded-navigation.ts", parser: "TYPESCRIPT_AST" };
        case "flutter":
            return { sourcePath: "lib/elmos_bounded_interaction.dart", compatibilityPath: "lib/elmos_bounded_navigation.dart", parser: "DART_BOUNDED_BASE64" };
        case "harmony-arkui":
            return { sourcePath: "entry/src/main/ets/elmos-bounded-interaction.ets", compatibilityPath: "entry/src/main/ets/elmos-bounded-navigation.ets", parser: "TYPESCRIPT_AST" };
        case "vue3":
        case "react":
        case "jquery":
        case "angular":
        case "svelte":
            return { sourcePath: "src/elmos-bounded-interaction.ts", compatibilityPath: "src/elmos-bounded-navigation.ts", parser: "TYPESCRIPT_AST" };
    }
}
function routeModel(request) {
    const components = new Map(request.uiIr.components.map(component => [component.id, component]));
    return request.uiIr.routes.map(route => {
        const component = components.get(route.componentId);
        if (!component)
            throw new Error(`interaction route component is missing: ${route.componentId}`);
        return {
            id: route.id,
            path: route.path,
            title: component.name,
            text: component.text,
            requiresAuth: route.requiresAuth,
            deepLink: route.deepLink,
        };
    });
}
export function canonicalBoundedFrontendInteractionModel(request) {
    const routes = routeModel(request);
    if (routes.length === 0)
        throw new Error("bounded interaction requires at least one route");
    const ir = request.uiIr;
    return {
        schemaVersion: "1.0",
        profile: "bounded-frontend-interaction-v1",
        projectTitle: request.title,
        navigation: { label: ir.accessibilityFocus.navigationLabel, fallback: "FIRST_DECLARED_ROUTE", routes },
        componentTemplate: {
            componentId: ir.componentTemplate.componentId,
            templateKind: ir.componentTemplate.templateKind,
            keyedBy: ir.componentTemplate.keyedBy,
            titleBinding: ir.componentTemplate.titleBinding,
            textBinding: ir.componentTemplate.textBinding,
        },
        stateManagement: {
            stateId: ir.stateManagement.stateId, initial: ir.stateManagement.initial, minimum: ir.stateManagement.minimum,
            maximum: ir.stateManagement.maximum, transition: ir.stateManagement.transition,
        },
        actionEvent: {
            acceptedEvents: ir.actionEvent.acceptedEvents,
            deniedAction: ir.actionEvent.deniedAction,
            keyboardSubmit: ir.actionEvent.keyboardSubmit,
        },
        effectLifecycle: {
            mountEffect: ir.effectLifecycle.mountEffect,
            cleanupEffect: ir.effectLifecycle.cleanupEffect,
            maxExecutionsPerMount: ir.effectLifecycle.maxExecutionsPerMount,
            staleResponsePolicy: ir.effectLifecycle.staleResponsePolicy,
        },
        formBindingValidation: {
            formId: ir.formBindingValidation.formId, fieldId: ir.formBindingValidation.fieldId,
            initialValue: ir.formBindingValidation.initialValue, required: ir.formBindingValidation.required,
            minimumLength: ir.formBindingValidation.minimumLength, validation: ir.formBindingValidation.validation,
            invalidCode: ir.formBindingValidation.invalidCode,
        },
        apiNetwork: {
            operationId: ir.apiNetwork.operationId, method: ir.apiNetwork.method, path: ir.apiNetwork.path,
            timeoutMs: ir.apiNetwork.timeoutMs, retry: ir.apiNetwork.retry, cacheScope: ir.apiNetwork.cacheScope,
            cancelOnUnmount: ir.apiNetwork.cancelOnUnmount,
        },
        identityPermission: {
            anonymousRole: ir.identityPermission.anonymousRole, authenticatedRole: ir.identityPermission.authenticatedRole,
            requiredPermission: ir.identityPermission.requiredPermission, deniedBehavior: ir.identityPermission.deniedBehavior,
            tenantIsolation: ir.identityPermission.tenantIsolation,
            serverAuthorityRequired: ir.identityPermission.serverAuthorityRequired,
        },
        renderingHydration: {
            mode: ir.renderingHydration.mode, hydrationPolicy: ir.renderingHydration.hydrationPolicy,
            mismatchBehavior: ir.renderingHydration.mismatchBehavior,
            duplicateEffectsAllowed: ir.renderingHydration.duplicateEffectsAllowed,
        },
        accessibilityFocus: {
            mainRole: ir.accessibilityFocus.mainRole, headingLevel: ir.accessibilityFocus.headingLevel,
            formLabel: ir.accessibilityFocus.formLabel, errorRole: ir.accessibilityFocus.errorRole,
            liveRegion: ir.accessibilityFocus.liveRegion, invalidFocusTarget: ir.accessibilityFocus.invalidFocusTarget,
            keyboardSubmit: ir.accessibilityFocus.keyboardSubmit,
        },
        i18nThemeResponsive: {
            supportedLocales: ir.i18nThemeResponsive.supportedLocales,
            fallbackLocale: ir.i18nThemeResponsive.fallbackLocale,
            themes: ir.i18nThemeResponsive.themes, defaultTheme: ir.i18nThemeResponsive.defaultTheme,
            compactBreakpoint: ir.i18nThemeResponsive.compactBreakpoint,
            compactColumns: ir.i18nThemeResponsive.compactColumns, wideColumns: ir.i18nThemeResponsive.wideColumns,
        },
        nativePlatform: {
            boundary: ir.nativePlatform.boundary, capability: ir.nativePlatform.capability,
            lifecycleStates: ir.nativePlatform.lifecycleStates, permission: ir.nativePlatform.permission,
            deniedBehavior: ir.nativePlatform.deniedBehavior, recovery: ir.nativePlatform.recovery,
        },
    };
}
function scenario(scenarioId, overrides) {
    return {
        scenarioId,
        input: {
            routePath: "/",
            event: "BOOT",
            counterBefore: 0,
            incrementCount: 0,
            lifecycle: "ACTIVE",
            query: "",
            keyboardKey: "NONE",
            authenticated: false,
            permissionGranted: false,
            tenantId: "tenant-a",
            resourceTenantId: "tenant-a",
            networkResult: "NONE",
            hydration: "NONE",
            locale: "zh-CN",
            theme: "LIGHT",
            viewportWidth: 1024,
            nativeLifecycle: "FOREGROUND",
            deepLinkPath: null,
            nativePermission: "GRANTED",
            nativeAvailable: true,
            ...overrides,
        },
    };
}
export function boundedInteractionScenarios(model) {
    const publicRoute = model.navigation.routes.find(route => !route.requiresAuth) ?? model.navigation.routes[0];
    const protectedRoute = model.navigation.routes.find(route => route.requiresAuth) ?? model.navigation.routes[0];
    const alternatePublicRoute = model.navigation.routes.find(route => !route.requiresAuth && route.id !== publicRoute.id) ?? publicRoute;
    return [
        scenario("BOOT_PUBLIC", { routePath: publicRoute.path, lifecycle: "MOUNT", hydration: "MATCH" }),
        scenario("NAVIGATE_PROTECTED_ANONYMOUS_DENIED", { routePath: protectedRoute.path, event: "NAVIGATE" }),
        scenario("AUTHENTICATE_AND_NAVIGATE_PROTECTED", { routePath: protectedRoute.path, event: "AUTHENTICATE", authenticated: true, permissionGranted: true, incrementCount: 1 }),
        scenario("FORM_INVALID_SUBMIT_FOCUS_ERROR", { routePath: protectedRoute.path, event: "SUBMIT", keyboardKey: "Enter", authenticated: true, permissionGranted: true, query: "x" }),
        scenario("FORM_VALID_SUBMIT_API_SUCCESS", { routePath: protectedRoute.path, event: "SUBMIT", keyboardKey: "Enter", authenticated: true, permissionGranted: true, query: "ok", networkResult: "SUCCESS", incrementCount: 3 }),
        scenario("API_ERROR_CANCEL_STALE_RESPONSE", { routePath: protectedRoute.path, event: "CANCEL", authenticated: true, permissionGranted: true, query: "fail", networkResult: "STALE", lifecycle: "UNMOUNT" }),
        scenario("HYDRATE_MATCH_SINGLE_EFFECT_CLEANUP", { routePath: publicRoute.path, event: "HYDRATE", lifecycle: "UNMOUNT", hydration: "MATCH" }),
        scenario("LOCALE_THEME_VIEWPORT_CHANGE", { routePath: publicRoute.path, event: "DISPLAY_CHANGE", locale: "fr-FR", theme: "DARK", viewportWidth: 480 }),
        scenario("NATIVE_DEEPLINK_BACKGROUND_PERMISSION_DENIED_RECOVERY", {
            routePath: publicRoute.path, event: "NATIVE_DEEPLINK", nativeLifecycle: "BACKGROUND",
            deepLinkPath: protectedRoute.path, nativePermission: "DENIED", nativeAvailable: true,
        }),
        scenario("TENANT_ISOLATION_MISMATCH_DENIED", {
            routePath: protectedRoute.path, event: "SUBMIT", authenticated: true, permissionGranted: true,
            tenantId: "tenant-a", resourceTenantId: "tenant-b", query: "ok", networkResult: "SUCCESS",
        }),
        scenario("API_NETWORK_ERROR", {
            routePath: protectedRoute.path, event: "SUBMIT", authenticated: true, permissionGranted: true,
            query: "ok", networkResult: "ERROR",
        }),
        scenario("HYDRATE_MISMATCH_ERROR", {
            routePath: publicRoute.path, event: "HYDRATE", lifecycle: "MOUNT", hydration: "MISMATCH",
        }),
        scenario("NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN", {
            routePath: publicRoute.path, event: "NATIVE_DEEPLINK", nativeLifecycle: "FOREGROUND",
            deepLinkPath: protectedRoute.path, nativePermission: "GRANTED", nativeAvailable: true,
            authenticated: true, permissionGranted: true,
        }),
        scenario("LOCALE_EN_US_WIDE_721", {
            routePath: publicRoute.path, event: "DISPLAY_CHANGE", locale: "en-US", theme: "LIGHT", viewportWidth: 721,
        }),
        scenario("UNSUPPORTED_THEME_FALLBACK", {
            routePath: publicRoute.path, event: "DISPLAY_CHANGE", locale: "zh-CN", theme: "SEPIA", viewportWidth: 1024,
        }),
        scenario("BREAKPOINT_720_COMPACT", {
            routePath: publicRoute.path, event: "DISPLAY_CHANGE", locale: "zh-CN", theme: "LIGHT", viewportWidth: 720,
        }),
        scenario("NAVIGATE_HELP_PUBLIC", { routePath: alternatePublicRoute.path, event: "NAVIGATE" }),
        scenario("KEYBOARD_ENTER_SUBMIT", {
            routePath: protectedRoute.path, event: "BOOT", keyboardKey: "Enter", authenticated: true,
            permissionGranted: true, query: "ok", networkResult: "SUCCESS",
        }),
    ];
}
export function observeBoundedFrontendInteraction(model, scenarioValue) {
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
}
function tsContract(model, javascript) {
    const scenarios = boundedInteractionScenarios(model);
    const typeSuffix = javascript ? "" : " as const";
    const parameter = javascript ? "scenario" : "scenario: (typeof ELMOS_INTERACTION_SCENARIOS)[number]";
    const rawReducer = observeBoundedFrontendInteraction.toString();
    const reducer = javascript ? rawReducer : rawReducer.replace("function observeBoundedFrontendInteraction(model, scenarioValue)", "function observeBoundedFrontendInteraction(model: typeof ELMOS_FRONTEND_INTERACTION, scenarioValue: (typeof ELMOS_INTERACTION_SCENARIOS)[number])");
    return [
        "// Generated sole executable semantic contract for bounded-frontend-interaction-v1.",
        `export const ELMOS_FRONTEND_INTERACTION = ${JSON.stringify(model, null, 2)}${typeSuffix};`,
        "export const ELMOS_INTERACTION_ROUTES = ELMOS_FRONTEND_INTERACTION.navigation.routes;",
        `export const ELMOS_INTERACTION_SCENARIOS = ${JSON.stringify(scenarios, null, 2)}${typeSuffix};`,
        "",
        `const ELMOS_INTERACTION_REDUCER = ${reducer};`,
        `export function elmosObserveInteraction(${parameter}) { return ELMOS_INTERACTION_REDUCER(ELMOS_FRONTEND_INTERACTION, scenario); }`,
        "",
    ].join("\n");
}
function tsNavigationCompatibility(profile) {
    const extension = profile === "vue2" ? "./elmos-bounded-interaction" : "./elmos-bounded-interaction";
    const typed = profile !== "vue2";
    return [
        "// Direct identity projection for bounded-navigation-v1 compatibility; no second route literal is permitted.",
        `import { ELMOS_FRONTEND_INTERACTION } from ${JSON.stringify(extension)};`,
        "export const ELMOS_BOUNDED_NAVIGATION = {",
        '  schemaVersion: "1.0", profile: "bounded-navigation-v1",',
        "  projectTitle: ELMOS_FRONTEND_INTERACTION.projectTitle,",
        "  navigation: { label: ELMOS_FRONTEND_INTERACTION.navigation.label },",
        '  render: { mainRole: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.mainRole, headingLevel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.headingLevel },',
        '  fallback: { strategy: ELMOS_FRONTEND_INTERACTION.navigation.fallback },',
        "  routes: ELMOS_FRONTEND_INTERACTION.navigation.routes,",
        `}${typed ? " as const" : ""};`,
        "export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes;",
        "",
        `export function elmosSelectBoundedRoute(path${typed ? ": string" : ""}) {`,
        "  const selected = ELMOS_ROUTES.find(route => route.path === path);",
        "  const fallback = ELMOS_ROUTES[0];",
        '  if (!fallback) throw new Error("bounded navigation requires at least one route");',
        "  return selected ?? fallback;",
        "}",
        "",
    ].join("\n");
}
function dartContract(model) {
    const encoded = Buffer.from(JSON.stringify(model), "utf8").toString("base64");
    const scenarios = Buffer.from(JSON.stringify(boundedInteractionScenarios(model)), "utf8").toString("base64");
    return [
        "// Generated sole executable semantic contract for bounded-frontend-interaction-v1.",
        "import 'dart:convert';",
        "",
        `const String elmosFrontendInteractionBase64 = ${JSON.stringify(encoded)};`,
        "final Map<String, Object?> elmosFrontendInteraction =",
        "    jsonDecode(utf8.decode(base64Decode(elmosFrontendInteractionBase64))) as Map<String, Object?>;",
        "final Map<String, Object?> elmosFrontendInteractionNavigation =",
        "    elmosFrontendInteraction['navigation']! as Map<String, Object?>;",
        `const String elmosInteractionScenariosBase64 = ${JSON.stringify(scenarios)};`,
        "final List<Object?> elmosInteractionScenarios =",
        "    jsonDecode(utf8.decode(base64Decode(elmosInteractionScenariosBase64))) as List<Object?>;",
        "Map<String, Object?> elmosMap(Object? value) => value! as Map<String, Object?>;",
        "List<Object?> elmosList(Object? value) => value! as List<Object?>;",
        "Map<String, Object?> elmosObserveInteraction(Object? rawScenario) {",
        "  final model = elmosFrontendInteraction; final scenario = elmosMap(rawScenario); final input = elmosMap(scenario['input']);",
        "  final navigation = elmosMap(model['navigation']); final routes = elmosList(navigation['routes']); final first = elmosMap(routes.first);",
        "  final requested = routes.map(elmosMap).firstWhere((route) => route['path'] == input['routePath'], orElse: () => first);",
        "  final identity = elmosMap(model['identityPermission']); final tenantMatch = identity['tenantIsolation'] == 'EXACT_TENANT_MATCH' && input['tenantId'] == input['resourceTenantId'];",
        "  final authorized = requested['requiresAuth'] != true || (input['authenticated'] == true && input['permissionGranted'] == true && tenantMatch);",
        "  final selected = authorized ? requested : first; final form = elmosMap(model['formBindingValidation']);",
        "  final rawQuery = input['query']! as String; final boundQuery = rawQuery.isEmpty ? form['initialValue']! as String : rawQuery;",
        "  final valid = (form['required'] != true || boundQuery.isNotEmpty) && boundQuery.length >= (form['minimumLength']! as num);",
        "  final action = elmosMap(model['actionEvent']); final submitted = input['event'] == 'SUBMIT' || input['keyboardKey'] == action['keyboardSubmit'];",
        "  final validated = form['validation'] == 'ON_SUBMIT' ? submitted : true; final apiCalled = validated && valid && authorized;",
        "  final api = elmosMap(model['apiNetwork']); final canceled = input['event'] == 'CANCEL' || (api['cancelOnUnmount'] == true && input['lifecycle'] == 'UNMOUNT');",
        "  final state = elmosMap(model['stateManagement']); final counterBase = (input['counterBefore']! as num).clamp(state['initial']! as num, double.infinity); final rawCounter = counterBase + (input['incrementCount']! as num);",
        "  final counterAfter = state['transition'] == 'SATURATING_INCREMENT' ? rawCounter.clamp(state['minimum']! as num, state['maximum']! as num) : counterBase;",
        "  final effect = elmosMap(model['effectLifecycle']);",
        "  final rendering = elmosMap(model['renderingHydration']); final a11y = elmosMap(model['accessibilityFocus']);",
        "  final display = elmosMap(model['i18nThemeResponsive']); final native = elmosMap(model['nativePlatform']);",
        "  final locale = elmosList(display['supportedLocales']).contains(input['locale']) ? input['locale'] : display['fallbackLocale'];",
        "  final theme = elmosList(display['themes']).contains(input['theme']) ? input['theme'] : display['defaultTheme'];",
        "  final formError = validated && !valid ? form['invalidCode'] : null; final focusTarget = formError == null ? (submitted ? 'result' : null) : a11y['invalidFocusTarget'];",
        "  final nativeTarget = input['deepLinkPath'] == null ? null : routes.map(elmosMap).firstWhere((route) => route['path'] == input['deepLinkPath'], orElse: () => first);",
        "  final nativeTargetAuthorized = nativeTarget == null || nativeTarget['requiresAuth'] != true || (input['authenticated'] == true && input['permissionGranted'] == true && tenantMatch);",
        "  final nativeAttempted = input['event'] == 'NATIVE_DEEPLINK' && input['deepLinkPath'] != null && native['capability'] == 'OPEN_DEEP_LINK';",
        "  final nativeLifecycleKnown = elmosList(native['lifecycleStates']).contains(input['nativeLifecycle']);",
        "  final nativeAllowed = nativeAttempted && input['nativeAvailable'] == true && input['nativePermission'] == 'GRANTED' && input['nativeLifecycle'] == 'FOREGROUND' && nativeLifecycleKnown && nativeTargetAuthorized;",
        "  return <String, Object?>{'scenarioId': scenario['scenarioId'], 'before': <String, Object?>{'counter': input['counterBefore'], 'lifecycle': input['lifecycle'], 'query': input['query'], 'authenticated': input['authenticated']},",
        "    'after': <String, Object?>{'counter': counterAfter, 'selectedRouteId': selected['id'], 'authorized': authorized, 'apiCalled': apiCalled, 'focusTarget': focusTarget, 'nativeAllowed': nativeAllowed}, 'blocks': <String, Object?>{",
        "      'route-navigation-deeplink-404': <String, Object?>{'requestedPath': input['routePath'], 'selectedRouteId': selected['id'], 'selectedPath': selected['path'], 'resolution': requested == first && input['routePath'] != first['path'] ? 'FIRST_DECLARED_FALLBACK' : authorized ? 'DECLARED' : 'AUTH_DENIED_FALLBACK', 'navigationLabel': navigation['label'], 'fallback': navigation['fallback'], 'deepLink': selected['deepLink'], 'requiresAuth': selected['requiresAuth']},",
        "      'component-template-view': <String, Object?>{'componentId': elmosMap(model['componentTemplate'])['componentId'], 'templateKind': elmosMap(model['componentTemplate'])['templateKind'], 'keyedBy': elmosMap(model['componentTemplate'])['keyedBy'], 'titleBinding': elmosMap(model['componentTemplate'])['titleBinding'], 'textBinding': elmosMap(model['componentTemplate'])['textBinding'], 'key': elmosMap(model['componentTemplate'])['keyedBy'] == 'route.id' ? selected['id'] : '', 'title': elmosMap(model['componentTemplate'])['titleBinding'] == 'route.title' ? selected['title'] : '', 'text': elmosMap(model['componentTemplate'])['textBinding'] == 'route.text' ? selected['text'] : '', 'visible': true},",
        "      'state-management': <String, Object?>{'stateId': state['stateId'], 'initial': state['initial'], 'minimum': state['minimum'], 'maximum': state['maximum'], 'transition': state['transition'], 'before': input['counterBefore'], 'after': counterAfter, 'saturated': rawCounter > (state['maximum']! as num)},",
        "      'action-event': <String, Object?>{'event': input['event'], 'keyboardKey': input['keyboardKey'], 'handled': elmosList(action['acceptedEvents']).contains(input['event']), 'action': submitted ? (valid && authorized ? 'SUBMIT_ACCEPTED' : action['deniedAction']) : input['event']},",
        "      'effect-lifecycle': <String, Object?>{'lifecycle': input['lifecycle'], 'mountEffect': input['lifecycle'] == 'MOUNT' ? effect['mountEffect'] : 'NONE', 'cleanupEffect': input['lifecycle'] == 'UNMOUNT' ? effect['cleanupEffect'] : 'NONE', 'maxExecutionsPerMount': effect['maxExecutionsPerMount'], 'staleResponsePolicy': effect['staleResponsePolicy'], 'executions': input['lifecycle'] == 'MOUNT' ? effect['maxExecutionsPerMount'] : 0, 'cleanup': input['lifecycle'] == 'UNMOUNT', 'staleResponseIgnored': input['networkResult'] == 'STALE' && canceled && effect['staleResponsePolicy'] == 'IGNORE_AFTER_CANCEL'},",
        "      'form-binding-validation': <String, Object?>{'formId': form['formId'], 'fieldId': form['fieldId'], 'initialValue': form['initialValue'], 'required': form['required'], 'minimumLength': form['minimumLength'], 'validation': form['validation'], 'value': boundQuery, 'submitted': submitted, 'validated': validated, 'valid': valid, 'errorCode': formError},",
        "      'api-network': <String, Object?>{'operationId': api['operationId'], 'called': apiCalled, 'method': api['method'], 'path': api['path'], 'timeoutMs': api['timeoutMs'], 'retry': api['retry'], 'cacheScope': api['cacheScope'], 'cancelOnUnmount': api['cancelOnUnmount'], 'outcome': !apiCalled ? 'NOT_CALLED' : canceled ? 'CANCELED' : input['networkResult'] == 'SUCCESS' ? 'SUCCESS' : input['networkResult'] == 'ERROR' ? 'ERROR' : 'PENDING', 'canceled': canceled, 'staleIgnored': input['networkResult'] == 'STALE' && canceled && effect['staleResponsePolicy'] == 'IGNORE_AFTER_CANCEL', 'cacheKey': api['cacheScope'] == 'TENANT_QUERY' ? '${input['tenantId']}:$boundQuery' : boundQuery},",
        "      'identity-permission': <String, Object?>{'role': input['authenticated'] == true ? identity['authenticatedRole'] : identity['anonymousRole'], 'permission': identity['requiredPermission'], 'permissionGranted': input['permissionGranted'], 'deniedBehavior': identity['deniedBehavior'], 'tenantIsolation': identity['tenantIsolation'], 'tenantMatch': tenantMatch, 'authorized': authorized, 'serverAuthorityRequired': identity['serverAuthorityRequired']},",
        "      'rendering-hydration': <String, Object?>{'mode': rendering['mode'], 'hydrationPolicy': rendering['hydrationPolicy'], 'requested': input['hydration'], 'status': input['hydration'] == 'MISMATCH' && rendering['hydrationPolicy'] == 'REQUIRE_MATCH' ? rendering['mismatchBehavior'] : input['hydration'] == 'MATCH' ? 'MATCHED' : 'NOT_ATTEMPTED', 'duplicateEffectsAllowed': rendering['duplicateEffectsAllowed'], 'duplicateEffects': rendering['duplicateEffectsAllowed'] == true && input['hydration'] == 'MISMATCH', 'mismatchVisible': input['hydration'] == 'MISMATCH'},",
        "      'accessibility-focus': <String, Object?>{'mainRole': a11y['mainRole'], 'headingLevel': a11y['headingLevel'], 'formLabel': a11y['formLabel'], 'errorRole': formError == null ? null : a11y['errorRole'], 'liveRegion': a11y['liveRegion'], 'keyboardSubmit': input['keyboardKey'] == a11y['keyboardSubmit'], 'focusTarget': focusTarget},",
        "      'i18n-theme-responsive': <String, Object?>{'requestedLocale': input['locale'], 'localeSupported': elmosList(display['supportedLocales']).contains(input['locale']), 'locale': locale, 'requestedTheme': input['theme'], 'themeSupported': elmosList(display['themes']).contains(input['theme']), 'theme': theme, 'viewportWidth': input['viewportWidth'], 'columns': (input['viewportWidth']! as num) <= (display['compactBreakpoint']! as num) ? display['compactColumns'] : display['wideColumns']},",
        "      'native-platform': <String, Object?>{'boundary': native['boundary'], 'capability': native['capability'], 'lifecycleStates': elmosList(native['lifecycleStates']).join('|'), 'lifecycle': input['nativeLifecycle'], 'lifecycleKnown': nativeLifecycleKnown, 'deepLinkPath': input['deepLinkPath'], 'targetRouteId': nativeTarget?['id'], 'targetAuthorized': nativeTargetAuthorized, 'attempted': nativeAttempted, 'permissionContract': native['permission'], 'permission': input['nativePermission'], 'available': input['nativeAvailable'], 'deniedBehavior': native['deniedBehavior'], 'outcome': !nativeAttempted ? 'NOT_ATTEMPTED' : nativeAllowed ? 'OPENED' : native['deniedBehavior'], 'recovery': nativeAllowed ? 'NOT_REQUIRED' : native['recovery']},",
        "    }};",
        "}",
        "",
    ].join("\n");
}
function dartNavigationCompatibility() {
    return [
        "// Direct identity projection for bounded-navigation-v1 compatibility; no second route literal is permitted.",
        "import 'elmos_bounded_interaction.dart';",
        "",
        "typedef ElmosBoundedRoute = Map<String, Object?>;",
        "extension ElmosBoundedRouteFields on ElmosBoundedRoute {",
        "  String get id => this['id']! as String;",
        "  String get path => this['path']! as String;",
        "  String get title => this['title']! as String;",
        "  String get text => this['text']! as String;",
        "  bool get requiresAuth => this['requiresAuth']! as bool;",
        "  bool get deepLink => this['deepLink']! as bool;",
        "}",
        "final Map<String, Object?> elmosBoundedNavigation = <String, Object?>{",
        "  'routes': elmosFrontendInteractionNavigation['routes']!,",
        "};",
        "final List<Object?> elmosBoundedRoutes = elmosBoundedNavigation['routes']! as List<Object?>;",
        "ElmosBoundedRoute elmosRoute(Object? raw) => raw! as ElmosBoundedRoute;",
        "ElmosBoundedRoute get elmosFirstRoute => elmosRoute(elmosBoundedRoutes.first);",
        "ElmosBoundedRoute elmosSelectBoundedRoute(String path) {",
        "  if (elmosBoundedRoutes.isEmpty) throw StateError('bounded navigation requires at least one route');",
        "  return elmosRoute(elmosBoundedRoutes.firstWhere((raw) => elmosRoute(raw).path == path, orElse: () => elmosBoundedRoutes.first));",
        "}",
        "",
    ].join("\n");
}
export function interactionContractSource(profile, model) {
    return profile === "flutter" ? dartContract(model) : tsContract(model, profile === "vue2");
}
export function navigationCompatibilitySource(profile) {
    return profile === "flutter" ? dartNavigationCompatibility() : tsNavigationCompatibility(profile);
}
//# sourceMappingURL=bounded-interaction-source.js.map