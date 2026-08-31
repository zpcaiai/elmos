Page({
  data: {
    activeIndex: 0,
    apiBaseUrl: "",
    components: [
    {
        "index": 0,
        "name": "AccountOrganizationStudio",
        "tag": "account-organization-studio"
    },
    {
        "index": 1,
        "name": "AccountWalletPanel",
        "tag": "account-wallet-panel"
    },
    {
        "index": 2,
        "name": "EventTable",
        "tag": "event-table"
    },
    {
        "index": 3,
        "name": "OperationsAdmin",
        "tag": "operations-admin"
    },
    {
        "index": 4,
        "name": "PlatformJobsPanel",
        "tag": "platform-jobs-panel"
    },
    {
        "index": 5,
        "name": "PlatformWalletPanel",
        "tag": "platform-wallet-panel"
    },
    {
        "index": 6,
        "name": "CommercializationConsole",
        "tag": "commercialization-console"
    },
    {
        "index": 7,
        "name": "AccountSessionProvider",
        "tag": "account-session-provider"
    },
    {
        "index": 8,
        "name": "AppShell",
        "tag": "app-shell"
    },
    {
        "index": 9,
        "name": "Icon",
        "tag": "icon"
    },
    {
        "index": 10,
        "name": "EquivalenceMatrix",
        "tag": "equivalence-matrix"
    },
    {
        "index": 11,
        "name": "EvidenceGraph",
        "tag": "evidence-graph"
    },
    {
        "index": 12,
        "name": "ProjectEvidenceCharts",
        "tag": "project-evidence-charts"
    },
    {
        "index": 13,
        "name": "RuntimeDeploymentGuide",
        "tag": "runtime-deployment-guide"
    },
    {
        "index": 14,
        "name": "SmokeRunButton",
        "tag": "smoke-run-button"
    },
    {
        "index": 15,
        "name": "UiPreferencesProvider",
        "tag": "ui-preferences-provider"
    },
    {
        "index": 16,
        "name": "FrontendTransformationStudio",
        "tag": "frontend-transformation-studio"
    },
    {
        "index": 17,
        "name": "ProjectGenerationStudio",
        "tag": "project-generation-studio"
    },
    {
        "index": 18,
        "name": "GovernanceWorkspace",
        "tag": "governance-workspace"
    },
    {
        "index": 19,
        "name": "HelpCenter",
        "tag": "help-center"
    },
    {
        "index": 20,
        "name": "MultimodalIntakeWorkbench",
        "tag": "multimodal-intake-workbench"
    },
    {
        "index": 21,
        "name": "RootLayout",
        "tag": "root-layout"
    },
    {
        "index": 22,
        "name": "LoginPage",
        "tag": "login-page"
    },
    {
        "index": 23,
        "name": "MigrationStudio",
        "tag": "migration-studio"
    },
    {
        "index": 24,
        "name": "ChinaDbSqlPreflightStudio",
        "tag": "china-db-sql-preflight-studio"
    },
    {
        "index": 25,
        "name": "ObservabilityWorkspace",
        "tag": "observability-workspace"
    },
    {
        "index": 26,
        "name": "RepositoryOrchestratorWorkbench",
        "tag": "repository-orchestrator-workbench"
    },
    {
        "index": 27,
        "name": "PlaygroundPage",
        "tag": "playground-page"
    },
    {
        "index": 28,
        "name": "PlaygroundWorkspace",
        "tag": "playground-workspace"
    },
    {
        "index": 29,
        "name": "PlanBillingAction",
        "tag": "plan-billing-action"
    },
    {
        "index": 30,
        "name": "SubscriptionManager",
        "tag": "subscription-manager"
    },
    {
        "index": 31,
        "name": "PricingPage",
        "tag": "pricing-page"
    },
    {
        "index": 32,
        "name": "UsageDashboard",
        "tag": "usage-dashboard"
    },
    {
        "index": 33,
        "name": "ModernizationProofStudio",
        "tag": "modernization-proof-studio"
    },
    {
        "index": 34,
        "name": "RegisterPage",
        "tag": "register-page"
    },
    {
        "index": 35,
        "name": "RepositoryWorkspaceStudio",
        "tag": "repository-workspace-studio"
    },
    {
        "index": 36,
        "name": "PrecisionMigrationJobs",
        "tag": "precision-migration-jobs"
    },
    {
        "index": 37,
        "name": "SkillsWorkspace",
        "tag": "skills-workspace"
    },
    {
        "index": 38,
        "name": "SpringModernizationStudio",
        "tag": "spring-modernization-studio"
    },
    {
        "index": 39,
        "name": "TranslationStudio",
        "tag": "translation-studio"
    }
]
  },
  selectComponent(event) { this.setData({ activeIndex: Number(event.currentTarget.dataset.index) }); },
  setApiBaseUrl(event) { this.setData({ apiBaseUrl: event.detail.value }); }
});
