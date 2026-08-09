# Frontend v2 formal-equivalence gap inventory

This inventory is exact for 9 profiles, 72 directed routes, 12 semantic blocks and 18 scenarios. Model/formal proof claims are kept separate from actual runtime and independent evidence.

| dimension | status | blocking reason |
| --- | --- | --- |
| model | PASSED | bounded same-engine relift model only |
| formal | PROVED_UNDER_ASSUMPTIONS | bounded Z3 encoding under explicit assumptions |
| browser | NOT_RUN | derived from applicable endpoint channels and route cross-channel closure |
| native | NOT_RUN | derived from applicable native endpoints and native-to-native route closure only |
| android | NOT_RUN | derived from exact applicable Android profile channels |
| ios | NOT_RUN | derived from exact applicable iOS profile channels |
| harmonyos | NOT_RUN | derived from the exact HarmonyOS profile channel |
| runtime | NOT_RUN | all required endpoint observations plus channel-specific canonical projections |
| independent | NOT_RUN | derived from signed external route/block evidence; same producer never upgrades this dimension |
| holdout | NOT_RUN | derived from independently attested holdout corpus provenance |
| representative | NOT_RUN | derived from independently attested representative workload provenance |

| route | block | model | formal | browser | android | ios | harmonyos | independent | certification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- frontend-v2-gap-row route=angular--to--flutter block=route-navigation-deeplink-404 -->
| angular--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=component-template-view -->
| angular--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=state-management -->
| angular--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=action-event -->
| angular--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=effect-lifecycle -->
| angular--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=form-binding-validation -->
| angular--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=api-network -->
| angular--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=identity-permission -->
| angular--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=rendering-hydration -->
| angular--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=accessibility-focus -->
| angular--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=i18n-theme-responsive -->
| angular--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--flutter block=native-platform -->
| angular--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=route-navigation-deeplink-404 -->
| angular--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=component-template-view -->
| angular--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=state-management -->
| angular--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=action-event -->
| angular--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=effect-lifecycle -->
| angular--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=form-binding-validation -->
| angular--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=api-network -->
| angular--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=identity-permission -->
| angular--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=rendering-hydration -->
| angular--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=accessibility-focus -->
| angular--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=i18n-theme-responsive -->
| angular--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--harmony-arkui block=native-platform -->
| angular--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=route-navigation-deeplink-404 -->
| angular--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=component-template-view -->
| angular--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=state-management -->
| angular--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=action-event -->
| angular--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=effect-lifecycle -->
| angular--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=form-binding-validation -->
| angular--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=api-network -->
| angular--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=identity-permission -->
| angular--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=rendering-hydration -->
| angular--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=accessibility-focus -->
| angular--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=i18n-theme-responsive -->
| angular--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--jquery block=native-platform -->
| angular--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=route-navigation-deeplink-404 -->
| angular--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=component-template-view -->
| angular--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=state-management -->
| angular--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=action-event -->
| angular--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=effect-lifecycle -->
| angular--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=form-binding-validation -->
| angular--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=api-network -->
| angular--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=identity-permission -->
| angular--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=rendering-hydration -->
| angular--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=accessibility-focus -->
| angular--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=i18n-theme-responsive -->
| angular--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react block=native-platform -->
| angular--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=route-navigation-deeplink-404 -->
| angular--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=component-template-view -->
| angular--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=state-management -->
| angular--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=action-event -->
| angular--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=effect-lifecycle -->
| angular--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=form-binding-validation -->
| angular--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=api-network -->
| angular--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=identity-permission -->
| angular--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=rendering-hydration -->
| angular--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=accessibility-focus -->
| angular--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=i18n-theme-responsive -->
| angular--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--react-native block=native-platform -->
| angular--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=route-navigation-deeplink-404 -->
| angular--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=component-template-view -->
| angular--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=state-management -->
| angular--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=action-event -->
| angular--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=effect-lifecycle -->
| angular--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=form-binding-validation -->
| angular--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=api-network -->
| angular--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=identity-permission -->
| angular--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=rendering-hydration -->
| angular--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=accessibility-focus -->
| angular--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=i18n-theme-responsive -->
| angular--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--svelte block=native-platform -->
| angular--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=route-navigation-deeplink-404 -->
| angular--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=component-template-view -->
| angular--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=state-management -->
| angular--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=action-event -->
| angular--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=effect-lifecycle -->
| angular--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=form-binding-validation -->
| angular--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=api-network -->
| angular--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=identity-permission -->
| angular--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=rendering-hydration -->
| angular--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=accessibility-focus -->
| angular--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=i18n-theme-responsive -->
| angular--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue2 block=native-platform -->
| angular--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=route-navigation-deeplink-404 -->
| angular--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=component-template-view -->
| angular--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=state-management -->
| angular--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=action-event -->
| angular--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=effect-lifecycle -->
| angular--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=form-binding-validation -->
| angular--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=api-network -->
| angular--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=identity-permission -->
| angular--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=rendering-hydration -->
| angular--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=accessibility-focus -->
| angular--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=i18n-theme-responsive -->
| angular--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=angular--to--vue3 block=native-platform -->
| angular--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=route-navigation-deeplink-404 -->
| flutter--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=component-template-view -->
| flutter--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=state-management -->
| flutter--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=action-event -->
| flutter--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=effect-lifecycle -->
| flutter--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=form-binding-validation -->
| flutter--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=api-network -->
| flutter--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=identity-permission -->
| flutter--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=rendering-hydration -->
| flutter--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=accessibility-focus -->
| flutter--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=i18n-theme-responsive -->
| flutter--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--angular block=native-platform -->
| flutter--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=route-navigation-deeplink-404 -->
| flutter--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=component-template-view -->
| flutter--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=state-management -->
| flutter--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=action-event -->
| flutter--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=effect-lifecycle -->
| flutter--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=form-binding-validation -->
| flutter--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=api-network -->
| flutter--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=identity-permission -->
| flutter--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=rendering-hydration -->
| flutter--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=accessibility-focus -->
| flutter--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=i18n-theme-responsive -->
| flutter--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--harmony-arkui block=native-platform -->
| flutter--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=route-navigation-deeplink-404 -->
| flutter--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=component-template-view -->
| flutter--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=state-management -->
| flutter--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=action-event -->
| flutter--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=effect-lifecycle -->
| flutter--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=form-binding-validation -->
| flutter--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=api-network -->
| flutter--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=identity-permission -->
| flutter--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=rendering-hydration -->
| flutter--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=accessibility-focus -->
| flutter--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=i18n-theme-responsive -->
| flutter--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--jquery block=native-platform -->
| flutter--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=route-navigation-deeplink-404 -->
| flutter--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=component-template-view -->
| flutter--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=state-management -->
| flutter--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=action-event -->
| flutter--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=effect-lifecycle -->
| flutter--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=form-binding-validation -->
| flutter--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=api-network -->
| flutter--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=identity-permission -->
| flutter--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=rendering-hydration -->
| flutter--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=accessibility-focus -->
| flutter--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=i18n-theme-responsive -->
| flutter--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react block=native-platform -->
| flutter--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=route-navigation-deeplink-404 -->
| flutter--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=component-template-view -->
| flutter--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=state-management -->
| flutter--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=action-event -->
| flutter--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=effect-lifecycle -->
| flutter--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=form-binding-validation -->
| flutter--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=api-network -->
| flutter--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=identity-permission -->
| flutter--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=rendering-hydration -->
| flutter--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=accessibility-focus -->
| flutter--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=i18n-theme-responsive -->
| flutter--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--react-native block=native-platform -->
| flutter--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=route-navigation-deeplink-404 -->
| flutter--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=component-template-view -->
| flutter--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=state-management -->
| flutter--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=action-event -->
| flutter--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=effect-lifecycle -->
| flutter--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=form-binding-validation -->
| flutter--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=api-network -->
| flutter--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=identity-permission -->
| flutter--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=rendering-hydration -->
| flutter--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=accessibility-focus -->
| flutter--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=i18n-theme-responsive -->
| flutter--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--svelte block=native-platform -->
| flutter--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=route-navigation-deeplink-404 -->
| flutter--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=component-template-view -->
| flutter--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=state-management -->
| flutter--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=action-event -->
| flutter--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=effect-lifecycle -->
| flutter--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=form-binding-validation -->
| flutter--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=api-network -->
| flutter--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=identity-permission -->
| flutter--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=rendering-hydration -->
| flutter--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=accessibility-focus -->
| flutter--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=i18n-theme-responsive -->
| flutter--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue2 block=native-platform -->
| flutter--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=route-navigation-deeplink-404 -->
| flutter--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=component-template-view -->
| flutter--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=state-management -->
| flutter--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=action-event -->
| flutter--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=effect-lifecycle -->
| flutter--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=form-binding-validation -->
| flutter--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=api-network -->
| flutter--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=identity-permission -->
| flutter--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=rendering-hydration -->
| flutter--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=accessibility-focus -->
| flutter--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=i18n-theme-responsive -->
| flutter--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=flutter--to--vue3 block=native-platform -->
| flutter--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=route-navigation-deeplink-404 -->
| harmony-arkui--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=component-template-view -->
| harmony-arkui--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=state-management -->
| harmony-arkui--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=action-event -->
| harmony-arkui--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=effect-lifecycle -->
| harmony-arkui--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=form-binding-validation -->
| harmony-arkui--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=api-network -->
| harmony-arkui--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=identity-permission -->
| harmony-arkui--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=rendering-hydration -->
| harmony-arkui--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=accessibility-focus -->
| harmony-arkui--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=i18n-theme-responsive -->
| harmony-arkui--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--angular block=native-platform -->
| harmony-arkui--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=route-navigation-deeplink-404 -->
| harmony-arkui--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=component-template-view -->
| harmony-arkui--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=state-management -->
| harmony-arkui--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=action-event -->
| harmony-arkui--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=effect-lifecycle -->
| harmony-arkui--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=form-binding-validation -->
| harmony-arkui--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=api-network -->
| harmony-arkui--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=identity-permission -->
| harmony-arkui--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=rendering-hydration -->
| harmony-arkui--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=accessibility-focus -->
| harmony-arkui--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=i18n-theme-responsive -->
| harmony-arkui--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--flutter block=native-platform -->
| harmony-arkui--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=route-navigation-deeplink-404 -->
| harmony-arkui--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=component-template-view -->
| harmony-arkui--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=state-management -->
| harmony-arkui--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=action-event -->
| harmony-arkui--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=effect-lifecycle -->
| harmony-arkui--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=form-binding-validation -->
| harmony-arkui--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=api-network -->
| harmony-arkui--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=identity-permission -->
| harmony-arkui--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=rendering-hydration -->
| harmony-arkui--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=accessibility-focus -->
| harmony-arkui--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=i18n-theme-responsive -->
| harmony-arkui--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--jquery block=native-platform -->
| harmony-arkui--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=route-navigation-deeplink-404 -->
| harmony-arkui--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=component-template-view -->
| harmony-arkui--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=state-management -->
| harmony-arkui--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=action-event -->
| harmony-arkui--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=effect-lifecycle -->
| harmony-arkui--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=form-binding-validation -->
| harmony-arkui--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=api-network -->
| harmony-arkui--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=identity-permission -->
| harmony-arkui--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=rendering-hydration -->
| harmony-arkui--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=accessibility-focus -->
| harmony-arkui--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=i18n-theme-responsive -->
| harmony-arkui--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react block=native-platform -->
| harmony-arkui--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=route-navigation-deeplink-404 -->
| harmony-arkui--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=component-template-view -->
| harmony-arkui--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=state-management -->
| harmony-arkui--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=action-event -->
| harmony-arkui--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=effect-lifecycle -->
| harmony-arkui--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=form-binding-validation -->
| harmony-arkui--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=api-network -->
| harmony-arkui--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=identity-permission -->
| harmony-arkui--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=rendering-hydration -->
| harmony-arkui--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=accessibility-focus -->
| harmony-arkui--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=i18n-theme-responsive -->
| harmony-arkui--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--react-native block=native-platform -->
| harmony-arkui--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=route-navigation-deeplink-404 -->
| harmony-arkui--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=component-template-view -->
| harmony-arkui--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=state-management -->
| harmony-arkui--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=action-event -->
| harmony-arkui--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=effect-lifecycle -->
| harmony-arkui--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=form-binding-validation -->
| harmony-arkui--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=api-network -->
| harmony-arkui--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=identity-permission -->
| harmony-arkui--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=rendering-hydration -->
| harmony-arkui--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=accessibility-focus -->
| harmony-arkui--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=i18n-theme-responsive -->
| harmony-arkui--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--svelte block=native-platform -->
| harmony-arkui--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=route-navigation-deeplink-404 -->
| harmony-arkui--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=component-template-view -->
| harmony-arkui--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=state-management -->
| harmony-arkui--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=action-event -->
| harmony-arkui--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=effect-lifecycle -->
| harmony-arkui--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=form-binding-validation -->
| harmony-arkui--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=api-network -->
| harmony-arkui--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=identity-permission -->
| harmony-arkui--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=rendering-hydration -->
| harmony-arkui--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=accessibility-focus -->
| harmony-arkui--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=i18n-theme-responsive -->
| harmony-arkui--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue2 block=native-platform -->
| harmony-arkui--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=route-navigation-deeplink-404 -->
| harmony-arkui--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=component-template-view -->
| harmony-arkui--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=state-management -->
| harmony-arkui--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=action-event -->
| harmony-arkui--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=effect-lifecycle -->
| harmony-arkui--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=form-binding-validation -->
| harmony-arkui--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=api-network -->
| harmony-arkui--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=identity-permission -->
| harmony-arkui--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=rendering-hydration -->
| harmony-arkui--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=accessibility-focus -->
| harmony-arkui--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=i18n-theme-responsive -->
| harmony-arkui--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=harmony-arkui--to--vue3 block=native-platform -->
| harmony-arkui--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=route-navigation-deeplink-404 -->
| jquery--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=component-template-view -->
| jquery--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=state-management -->
| jquery--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=action-event -->
| jquery--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=effect-lifecycle -->
| jquery--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=form-binding-validation -->
| jquery--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=api-network -->
| jquery--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=identity-permission -->
| jquery--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=rendering-hydration -->
| jquery--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=accessibility-focus -->
| jquery--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=i18n-theme-responsive -->
| jquery--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--angular block=native-platform -->
| jquery--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=route-navigation-deeplink-404 -->
| jquery--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=component-template-view -->
| jquery--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=state-management -->
| jquery--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=action-event -->
| jquery--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=effect-lifecycle -->
| jquery--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=form-binding-validation -->
| jquery--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=api-network -->
| jquery--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=identity-permission -->
| jquery--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=rendering-hydration -->
| jquery--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=accessibility-focus -->
| jquery--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=i18n-theme-responsive -->
| jquery--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--flutter block=native-platform -->
| jquery--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=route-navigation-deeplink-404 -->
| jquery--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=component-template-view -->
| jquery--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=state-management -->
| jquery--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=action-event -->
| jquery--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=effect-lifecycle -->
| jquery--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=form-binding-validation -->
| jquery--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=api-network -->
| jquery--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=identity-permission -->
| jquery--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=rendering-hydration -->
| jquery--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=accessibility-focus -->
| jquery--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=i18n-theme-responsive -->
| jquery--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--harmony-arkui block=native-platform -->
| jquery--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=route-navigation-deeplink-404 -->
| jquery--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=component-template-view -->
| jquery--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=state-management -->
| jquery--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=action-event -->
| jquery--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=effect-lifecycle -->
| jquery--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=form-binding-validation -->
| jquery--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=api-network -->
| jquery--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=identity-permission -->
| jquery--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=rendering-hydration -->
| jquery--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=accessibility-focus -->
| jquery--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=i18n-theme-responsive -->
| jquery--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react block=native-platform -->
| jquery--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=route-navigation-deeplink-404 -->
| jquery--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=component-template-view -->
| jquery--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=state-management -->
| jquery--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=action-event -->
| jquery--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=effect-lifecycle -->
| jquery--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=form-binding-validation -->
| jquery--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=api-network -->
| jquery--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=identity-permission -->
| jquery--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=rendering-hydration -->
| jquery--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=accessibility-focus -->
| jquery--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=i18n-theme-responsive -->
| jquery--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--react-native block=native-platform -->
| jquery--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=route-navigation-deeplink-404 -->
| jquery--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=component-template-view -->
| jquery--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=state-management -->
| jquery--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=action-event -->
| jquery--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=effect-lifecycle -->
| jquery--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=form-binding-validation -->
| jquery--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=api-network -->
| jquery--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=identity-permission -->
| jquery--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=rendering-hydration -->
| jquery--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=accessibility-focus -->
| jquery--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=i18n-theme-responsive -->
| jquery--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--svelte block=native-platform -->
| jquery--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=route-navigation-deeplink-404 -->
| jquery--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=component-template-view -->
| jquery--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=state-management -->
| jquery--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=action-event -->
| jquery--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=effect-lifecycle -->
| jquery--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=form-binding-validation -->
| jquery--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=api-network -->
| jquery--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=identity-permission -->
| jquery--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=rendering-hydration -->
| jquery--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=accessibility-focus -->
| jquery--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=i18n-theme-responsive -->
| jquery--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue2 block=native-platform -->
| jquery--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=route-navigation-deeplink-404 -->
| jquery--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=component-template-view -->
| jquery--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=state-management -->
| jquery--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=action-event -->
| jquery--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=effect-lifecycle -->
| jquery--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=form-binding-validation -->
| jquery--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=api-network -->
| jquery--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=identity-permission -->
| jquery--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=rendering-hydration -->
| jquery--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=accessibility-focus -->
| jquery--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=i18n-theme-responsive -->
| jquery--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=jquery--to--vue3 block=native-platform -->
| jquery--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=route-navigation-deeplink-404 -->
| react--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=component-template-view -->
| react--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=state-management -->
| react--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=action-event -->
| react--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=effect-lifecycle -->
| react--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=form-binding-validation -->
| react--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=api-network -->
| react--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=identity-permission -->
| react--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=rendering-hydration -->
| react--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=accessibility-focus -->
| react--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=i18n-theme-responsive -->
| react--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--angular block=native-platform -->
| react--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=route-navigation-deeplink-404 -->
| react--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=component-template-view -->
| react--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=state-management -->
| react--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=action-event -->
| react--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=effect-lifecycle -->
| react--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=form-binding-validation -->
| react--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=api-network -->
| react--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=identity-permission -->
| react--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=rendering-hydration -->
| react--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=accessibility-focus -->
| react--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=i18n-theme-responsive -->
| react--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--flutter block=native-platform -->
| react--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=route-navigation-deeplink-404 -->
| react--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=component-template-view -->
| react--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=state-management -->
| react--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=action-event -->
| react--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=effect-lifecycle -->
| react--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=form-binding-validation -->
| react--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=api-network -->
| react--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=identity-permission -->
| react--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=rendering-hydration -->
| react--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=accessibility-focus -->
| react--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=i18n-theme-responsive -->
| react--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--harmony-arkui block=native-platform -->
| react--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=route-navigation-deeplink-404 -->
| react--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=component-template-view -->
| react--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=state-management -->
| react--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=action-event -->
| react--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=effect-lifecycle -->
| react--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=form-binding-validation -->
| react--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=api-network -->
| react--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=identity-permission -->
| react--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=rendering-hydration -->
| react--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=accessibility-focus -->
| react--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=i18n-theme-responsive -->
| react--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--jquery block=native-platform -->
| react--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=route-navigation-deeplink-404 -->
| react--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=component-template-view -->
| react--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=state-management -->
| react--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=action-event -->
| react--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=effect-lifecycle -->
| react--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=form-binding-validation -->
| react--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=api-network -->
| react--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=identity-permission -->
| react--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=rendering-hydration -->
| react--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=accessibility-focus -->
| react--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=i18n-theme-responsive -->
| react--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--react-native block=native-platform -->
| react--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=route-navigation-deeplink-404 -->
| react--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=component-template-view -->
| react--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=state-management -->
| react--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=action-event -->
| react--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=effect-lifecycle -->
| react--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=form-binding-validation -->
| react--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=api-network -->
| react--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=identity-permission -->
| react--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=rendering-hydration -->
| react--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=accessibility-focus -->
| react--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=i18n-theme-responsive -->
| react--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--svelte block=native-platform -->
| react--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=route-navigation-deeplink-404 -->
| react--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=component-template-view -->
| react--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=state-management -->
| react--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=action-event -->
| react--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=effect-lifecycle -->
| react--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=form-binding-validation -->
| react--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=api-network -->
| react--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=identity-permission -->
| react--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=rendering-hydration -->
| react--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=accessibility-focus -->
| react--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=i18n-theme-responsive -->
| react--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue2 block=native-platform -->
| react--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=route-navigation-deeplink-404 -->
| react--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=component-template-view -->
| react--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=state-management -->
| react--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=action-event -->
| react--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=effect-lifecycle -->
| react--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=form-binding-validation -->
| react--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=api-network -->
| react--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=identity-permission -->
| react--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=rendering-hydration -->
| react--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=accessibility-focus -->
| react--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=i18n-theme-responsive -->
| react--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react--to--vue3 block=native-platform -->
| react--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=route-navigation-deeplink-404 -->
| react-native--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=component-template-view -->
| react-native--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=state-management -->
| react-native--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=action-event -->
| react-native--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=effect-lifecycle -->
| react-native--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=form-binding-validation -->
| react-native--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=api-network -->
| react-native--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=identity-permission -->
| react-native--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=rendering-hydration -->
| react-native--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=accessibility-focus -->
| react-native--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=i18n-theme-responsive -->
| react-native--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--angular block=native-platform -->
| react-native--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=route-navigation-deeplink-404 -->
| react-native--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=component-template-view -->
| react-native--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=state-management -->
| react-native--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=action-event -->
| react-native--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=effect-lifecycle -->
| react-native--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=form-binding-validation -->
| react-native--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=api-network -->
| react-native--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=identity-permission -->
| react-native--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=rendering-hydration -->
| react-native--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=accessibility-focus -->
| react-native--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=i18n-theme-responsive -->
| react-native--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--flutter block=native-platform -->
| react-native--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=route-navigation-deeplink-404 -->
| react-native--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=component-template-view -->
| react-native--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=state-management -->
| react-native--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=action-event -->
| react-native--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=effect-lifecycle -->
| react-native--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=form-binding-validation -->
| react-native--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=api-network -->
| react-native--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=identity-permission -->
| react-native--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=rendering-hydration -->
| react-native--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=accessibility-focus -->
| react-native--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=i18n-theme-responsive -->
| react-native--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--harmony-arkui block=native-platform -->
| react-native--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=route-navigation-deeplink-404 -->
| react-native--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=component-template-view -->
| react-native--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=state-management -->
| react-native--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=action-event -->
| react-native--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=effect-lifecycle -->
| react-native--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=form-binding-validation -->
| react-native--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=api-network -->
| react-native--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=identity-permission -->
| react-native--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=rendering-hydration -->
| react-native--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=accessibility-focus -->
| react-native--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=i18n-theme-responsive -->
| react-native--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--jquery block=native-platform -->
| react-native--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=route-navigation-deeplink-404 -->
| react-native--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=component-template-view -->
| react-native--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=state-management -->
| react-native--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=action-event -->
| react-native--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=effect-lifecycle -->
| react-native--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=form-binding-validation -->
| react-native--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=api-network -->
| react-native--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=identity-permission -->
| react-native--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=rendering-hydration -->
| react-native--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=accessibility-focus -->
| react-native--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=i18n-theme-responsive -->
| react-native--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--react block=native-platform -->
| react-native--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=route-navigation-deeplink-404 -->
| react-native--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=component-template-view -->
| react-native--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=state-management -->
| react-native--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=action-event -->
| react-native--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=effect-lifecycle -->
| react-native--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=form-binding-validation -->
| react-native--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=api-network -->
| react-native--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=identity-permission -->
| react-native--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=rendering-hydration -->
| react-native--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=accessibility-focus -->
| react-native--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=i18n-theme-responsive -->
| react-native--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--svelte block=native-platform -->
| react-native--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=route-navigation-deeplink-404 -->
| react-native--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=component-template-view -->
| react-native--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=state-management -->
| react-native--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=action-event -->
| react-native--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=effect-lifecycle -->
| react-native--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=form-binding-validation -->
| react-native--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=api-network -->
| react-native--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=identity-permission -->
| react-native--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=rendering-hydration -->
| react-native--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=accessibility-focus -->
| react-native--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=i18n-theme-responsive -->
| react-native--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue2 block=native-platform -->
| react-native--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=route-navigation-deeplink-404 -->
| react-native--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=component-template-view -->
| react-native--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=state-management -->
| react-native--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=action-event -->
| react-native--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=effect-lifecycle -->
| react-native--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=form-binding-validation -->
| react-native--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=api-network -->
| react-native--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=identity-permission -->
| react-native--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=rendering-hydration -->
| react-native--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=accessibility-focus -->
| react-native--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=i18n-theme-responsive -->
| react-native--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=react-native--to--vue3 block=native-platform -->
| react-native--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=route-navigation-deeplink-404 -->
| svelte--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=component-template-view -->
| svelte--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=state-management -->
| svelte--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=action-event -->
| svelte--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=effect-lifecycle -->
| svelte--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=form-binding-validation -->
| svelte--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=api-network -->
| svelte--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=identity-permission -->
| svelte--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=rendering-hydration -->
| svelte--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=accessibility-focus -->
| svelte--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=i18n-theme-responsive -->
| svelte--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--angular block=native-platform -->
| svelte--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=route-navigation-deeplink-404 -->
| svelte--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=component-template-view -->
| svelte--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=state-management -->
| svelte--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=action-event -->
| svelte--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=effect-lifecycle -->
| svelte--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=form-binding-validation -->
| svelte--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=api-network -->
| svelte--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=identity-permission -->
| svelte--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=rendering-hydration -->
| svelte--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=accessibility-focus -->
| svelte--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=i18n-theme-responsive -->
| svelte--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--flutter block=native-platform -->
| svelte--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=route-navigation-deeplink-404 -->
| svelte--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=component-template-view -->
| svelte--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=state-management -->
| svelte--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=action-event -->
| svelte--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=effect-lifecycle -->
| svelte--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=form-binding-validation -->
| svelte--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=api-network -->
| svelte--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=identity-permission -->
| svelte--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=rendering-hydration -->
| svelte--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=accessibility-focus -->
| svelte--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=i18n-theme-responsive -->
| svelte--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--harmony-arkui block=native-platform -->
| svelte--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=route-navigation-deeplink-404 -->
| svelte--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=component-template-view -->
| svelte--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=state-management -->
| svelte--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=action-event -->
| svelte--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=effect-lifecycle -->
| svelte--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=form-binding-validation -->
| svelte--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=api-network -->
| svelte--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=identity-permission -->
| svelte--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=rendering-hydration -->
| svelte--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=accessibility-focus -->
| svelte--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=i18n-theme-responsive -->
| svelte--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--jquery block=native-platform -->
| svelte--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=route-navigation-deeplink-404 -->
| svelte--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=component-template-view -->
| svelte--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=state-management -->
| svelte--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=action-event -->
| svelte--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=effect-lifecycle -->
| svelte--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=form-binding-validation -->
| svelte--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=api-network -->
| svelte--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=identity-permission -->
| svelte--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=rendering-hydration -->
| svelte--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=accessibility-focus -->
| svelte--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=i18n-theme-responsive -->
| svelte--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react block=native-platform -->
| svelte--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=route-navigation-deeplink-404 -->
| svelte--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=component-template-view -->
| svelte--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=state-management -->
| svelte--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=action-event -->
| svelte--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=effect-lifecycle -->
| svelte--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=form-binding-validation -->
| svelte--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=api-network -->
| svelte--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=identity-permission -->
| svelte--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=rendering-hydration -->
| svelte--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=accessibility-focus -->
| svelte--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=i18n-theme-responsive -->
| svelte--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--react-native block=native-platform -->
| svelte--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=route-navigation-deeplink-404 -->
| svelte--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=component-template-view -->
| svelte--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=state-management -->
| svelte--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=action-event -->
| svelte--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=effect-lifecycle -->
| svelte--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=form-binding-validation -->
| svelte--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=api-network -->
| svelte--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=identity-permission -->
| svelte--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=rendering-hydration -->
| svelte--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=accessibility-focus -->
| svelte--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=i18n-theme-responsive -->
| svelte--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue2 block=native-platform -->
| svelte--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=route-navigation-deeplink-404 -->
| svelte--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=component-template-view -->
| svelte--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=state-management -->
| svelte--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=action-event -->
| svelte--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=effect-lifecycle -->
| svelte--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=form-binding-validation -->
| svelte--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=api-network -->
| svelte--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=identity-permission -->
| svelte--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=rendering-hydration -->
| svelte--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=accessibility-focus -->
| svelte--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=i18n-theme-responsive -->
| svelte--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=svelte--to--vue3 block=native-platform -->
| svelte--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=route-navigation-deeplink-404 -->
| vue2--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=component-template-view -->
| vue2--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=state-management -->
| vue2--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=action-event -->
| vue2--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=effect-lifecycle -->
| vue2--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=form-binding-validation -->
| vue2--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=api-network -->
| vue2--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=identity-permission -->
| vue2--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=rendering-hydration -->
| vue2--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=accessibility-focus -->
| vue2--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=i18n-theme-responsive -->
| vue2--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--angular block=native-platform -->
| vue2--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=route-navigation-deeplink-404 -->
| vue2--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=component-template-view -->
| vue2--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=state-management -->
| vue2--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=action-event -->
| vue2--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=effect-lifecycle -->
| vue2--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=form-binding-validation -->
| vue2--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=api-network -->
| vue2--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=identity-permission -->
| vue2--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=rendering-hydration -->
| vue2--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=accessibility-focus -->
| vue2--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=i18n-theme-responsive -->
| vue2--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--flutter block=native-platform -->
| vue2--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=route-navigation-deeplink-404 -->
| vue2--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=component-template-view -->
| vue2--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=state-management -->
| vue2--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=action-event -->
| vue2--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=effect-lifecycle -->
| vue2--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=form-binding-validation -->
| vue2--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=api-network -->
| vue2--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=identity-permission -->
| vue2--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=rendering-hydration -->
| vue2--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=accessibility-focus -->
| vue2--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=i18n-theme-responsive -->
| vue2--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--harmony-arkui block=native-platform -->
| vue2--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=route-navigation-deeplink-404 -->
| vue2--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=component-template-view -->
| vue2--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=state-management -->
| vue2--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=action-event -->
| vue2--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=effect-lifecycle -->
| vue2--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=form-binding-validation -->
| vue2--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=api-network -->
| vue2--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=identity-permission -->
| vue2--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=rendering-hydration -->
| vue2--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=accessibility-focus -->
| vue2--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=i18n-theme-responsive -->
| vue2--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--jquery block=native-platform -->
| vue2--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=route-navigation-deeplink-404 -->
| vue2--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=component-template-view -->
| vue2--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=state-management -->
| vue2--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=action-event -->
| vue2--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=effect-lifecycle -->
| vue2--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=form-binding-validation -->
| vue2--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=api-network -->
| vue2--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=identity-permission -->
| vue2--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=rendering-hydration -->
| vue2--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=accessibility-focus -->
| vue2--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=i18n-theme-responsive -->
| vue2--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react block=native-platform -->
| vue2--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=route-navigation-deeplink-404 -->
| vue2--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=component-template-view -->
| vue2--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=state-management -->
| vue2--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=action-event -->
| vue2--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=effect-lifecycle -->
| vue2--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=form-binding-validation -->
| vue2--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=api-network -->
| vue2--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=identity-permission -->
| vue2--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=rendering-hydration -->
| vue2--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=accessibility-focus -->
| vue2--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=i18n-theme-responsive -->
| vue2--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--react-native block=native-platform -->
| vue2--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=route-navigation-deeplink-404 -->
| vue2--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=component-template-view -->
| vue2--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=state-management -->
| vue2--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=action-event -->
| vue2--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=effect-lifecycle -->
| vue2--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=form-binding-validation -->
| vue2--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=api-network -->
| vue2--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=identity-permission -->
| vue2--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=rendering-hydration -->
| vue2--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=accessibility-focus -->
| vue2--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=i18n-theme-responsive -->
| vue2--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--svelte block=native-platform -->
| vue2--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=route-navigation-deeplink-404 -->
| vue2--to--vue3 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=component-template-view -->
| vue2--to--vue3 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=state-management -->
| vue2--to--vue3 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=action-event -->
| vue2--to--vue3 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=effect-lifecycle -->
| vue2--to--vue3 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=form-binding-validation -->
| vue2--to--vue3 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=api-network -->
| vue2--to--vue3 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=identity-permission -->
| vue2--to--vue3 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=rendering-hydration -->
| vue2--to--vue3 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=accessibility-focus -->
| vue2--to--vue3 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=i18n-theme-responsive -->
| vue2--to--vue3 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue2--to--vue3 block=native-platform -->
| vue2--to--vue3 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=route-navigation-deeplink-404 -->
| vue3--to--angular | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=component-template-view -->
| vue3--to--angular | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=state-management -->
| vue3--to--angular | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=action-event -->
| vue3--to--angular | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=effect-lifecycle -->
| vue3--to--angular | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=form-binding-validation -->
| vue3--to--angular | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=api-network -->
| vue3--to--angular | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=identity-permission -->
| vue3--to--angular | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=rendering-hydration -->
| vue3--to--angular | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=accessibility-focus -->
| vue3--to--angular | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=i18n-theme-responsive -->
| vue3--to--angular | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--angular block=native-platform -->
| vue3--to--angular | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=route-navigation-deeplink-404 -->
| vue3--to--flutter | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=component-template-view -->
| vue3--to--flutter | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=state-management -->
| vue3--to--flutter | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=action-event -->
| vue3--to--flutter | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=effect-lifecycle -->
| vue3--to--flutter | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=form-binding-validation -->
| vue3--to--flutter | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=api-network -->
| vue3--to--flutter | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=identity-permission -->
| vue3--to--flutter | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=rendering-hydration -->
| vue3--to--flutter | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=accessibility-focus -->
| vue3--to--flutter | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=i18n-theme-responsive -->
| vue3--to--flutter | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--flutter block=native-platform -->
| vue3--to--flutter | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=route-navigation-deeplink-404 -->
| vue3--to--harmony-arkui | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=component-template-view -->
| vue3--to--harmony-arkui | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=state-management -->
| vue3--to--harmony-arkui | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=action-event -->
| vue3--to--harmony-arkui | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=effect-lifecycle -->
| vue3--to--harmony-arkui | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=form-binding-validation -->
| vue3--to--harmony-arkui | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=api-network -->
| vue3--to--harmony-arkui | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=identity-permission -->
| vue3--to--harmony-arkui | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=rendering-hydration -->
| vue3--to--harmony-arkui | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=accessibility-focus -->
| vue3--to--harmony-arkui | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=i18n-theme-responsive -->
| vue3--to--harmony-arkui | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--harmony-arkui block=native-platform -->
| vue3--to--harmony-arkui | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=route-navigation-deeplink-404 -->
| vue3--to--jquery | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=component-template-view -->
| vue3--to--jquery | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=state-management -->
| vue3--to--jquery | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=action-event -->
| vue3--to--jquery | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=effect-lifecycle -->
| vue3--to--jquery | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=form-binding-validation -->
| vue3--to--jquery | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=api-network -->
| vue3--to--jquery | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=identity-permission -->
| vue3--to--jquery | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=rendering-hydration -->
| vue3--to--jquery | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=accessibility-focus -->
| vue3--to--jquery | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=i18n-theme-responsive -->
| vue3--to--jquery | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--jquery block=native-platform -->
| vue3--to--jquery | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=route-navigation-deeplink-404 -->
| vue3--to--react | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=component-template-view -->
| vue3--to--react | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=state-management -->
| vue3--to--react | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=action-event -->
| vue3--to--react | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=effect-lifecycle -->
| vue3--to--react | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=form-binding-validation -->
| vue3--to--react | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=api-network -->
| vue3--to--react | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=identity-permission -->
| vue3--to--react | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=rendering-hydration -->
| vue3--to--react | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=accessibility-focus -->
| vue3--to--react | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=i18n-theme-responsive -->
| vue3--to--react | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react block=native-platform -->
| vue3--to--react | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=route-navigation-deeplink-404 -->
| vue3--to--react-native | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=component-template-view -->
| vue3--to--react-native | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=state-management -->
| vue3--to--react-native | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=action-event -->
| vue3--to--react-native | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=effect-lifecycle -->
| vue3--to--react-native | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=form-binding-validation -->
| vue3--to--react-native | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=api-network -->
| vue3--to--react-native | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=identity-permission -->
| vue3--to--react-native | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=rendering-hydration -->
| vue3--to--react-native | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=accessibility-focus -->
| vue3--to--react-native | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=i18n-theme-responsive -->
| vue3--to--react-native | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--react-native block=native-platform -->
| vue3--to--react-native | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=route-navigation-deeplink-404 -->
| vue3--to--svelte | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=component-template-view -->
| vue3--to--svelte | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=state-management -->
| vue3--to--svelte | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=action-event -->
| vue3--to--svelte | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=effect-lifecycle -->
| vue3--to--svelte | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=form-binding-validation -->
| vue3--to--svelte | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=api-network -->
| vue3--to--svelte | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=identity-permission -->
| vue3--to--svelte | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=rendering-hydration -->
| vue3--to--svelte | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=accessibility-focus -->
| vue3--to--svelte | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=i18n-theme-responsive -->
| vue3--to--svelte | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PARTIAL | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--svelte block=native-platform -->
| vue3--to--svelte | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=route-navigation-deeplink-404 -->
| vue3--to--vue2 | route-navigation-deeplink-404 | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=component-template-view -->
| vue3--to--vue2 | component-template-view | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=state-management -->
| vue3--to--vue2 | state-management | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=action-event -->
| vue3--to--vue2 | action-event | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=effect-lifecycle -->
| vue3--to--vue2 | effect-lifecycle | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=form-binding-validation -->
| vue3--to--vue2 | form-binding-validation | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=api-network -->
| vue3--to--vue2 | api-network | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=identity-permission -->
| vue3--to--vue2 | identity-permission | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=rendering-hydration -->
| vue3--to--vue2 | rendering-hydration | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=accessibility-focus -->
| vue3--to--vue2 | accessibility-focus | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=i18n-theme-responsive -->
| vue3--to--vue2 | i18n-theme-responsive | PASSED | PROVED_UNDER_ASSUMPTIONS | PASSED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
<!-- frontend-v2-gap-row route=vue3--to--vue2 block=native-platform -->
| vue3--to--vue2 | native-platform | PASSED | PROVED_UNDER_ASSUMPTIONS | NOT_RUN | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RUN | NOT_CERTIFIED |
