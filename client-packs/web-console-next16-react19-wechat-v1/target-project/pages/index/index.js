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
        "name": "CoverageMeter",
        "tag": "coverage-meter"
    },
    {
        "index": 11,
        "name": "EquivalenceMatrix",
        "tag": "equivalence-matrix"
    },
    {
        "index": 12,
        "name": "EvidenceGraph",
        "tag": "evidence-graph"
    },
    {
        "index": 13,
        "name": "ProjectEvidenceCharts",
        "tag": "project-evidence-charts"
    },
    {
        "index": 14,
        "name": "RuntimeDeploymentGuide",
        "tag": "runtime-deployment-guide"
    },
    {
        "index": 15,
        "name": "SmokeRunButton",
        "tag": "smoke-run-button"
    },
    {
        "index": 16,
        "name": "UiPreferencesProvider",
        "tag": "ui-preferences-provider"
    },
    {
        "index": 17,
        "name": "FrontendTransformationStudio",
        "tag": "frontend-transformation-studio"
    },
    {
        "index": 18,
        "name": "ProjectGenerationStudio",
        "tag": "project-generation-studio"
    },
    {
        "index": 19,
        "name": "GovernanceWorkspace",
        "tag": "governance-workspace"
    },
    {
        "index": 20,
        "name": "HelpCenter",
        "tag": "help-center"
    },
    {
        "index": 21,
        "name": "MultimodalIntakeWorkbench",
        "tag": "multimodal-intake-workbench"
    },
    {
        "index": 22,
        "name": "RootLayout",
        "tag": "root-layout"
    },
    {
        "index": 23,
        "name": "LoginPage",
        "tag": "login-page"
    },
    {
        "index": 24,
        "name": "MigrationStudio",
        "tag": "migration-studio"
    },
    {
        "index": 25,
        "name": "ChinaDbSqlPreflightStudio",
        "tag": "china-db-sql-preflight-studio"
    },
    {
        "index": 26,
        "name": "ObservabilityWorkspace",
        "tag": "observability-workspace"
    },
    {
        "index": 27,
        "name": "RepositoryOrchestratorWorkbench",
        "tag": "repository-orchestrator-workbench"
    },
    {
        "index": 28,
        "name": "PlaygroundPage",
        "tag": "playground-page"
    },
    {
        "index": 29,
        "name": "PlaygroundWorkspace",
        "tag": "playground-workspace"
    },
    {
        "index": 30,
        "name": "PlanBillingAction",
        "tag": "plan-billing-action"
    },
    {
        "index": 31,
        "name": "SubscriptionManager",
        "tag": "subscription-manager"
    },
    {
        "index": 32,
        "name": "PricingPage",
        "tag": "pricing-page"
    },
    {
        "index": 33,
        "name": "UsageDashboard",
        "tag": "usage-dashboard"
    },
    {
        "index": 34,
        "name": "ModernizationProofStudio",
        "tag": "modernization-proof-studio"
    },
    {
        "index": 35,
        "name": "RegisterPage",
        "tag": "register-page"
    },
    {
        "index": 36,
        "name": "RepositoryWorkspaceStudio",
        "tag": "repository-workspace-studio"
    },
    {
        "index": 37,
        "name": "PrecisionMigrationJobs",
        "tag": "precision-migration-jobs"
    },
    {
        "index": 38,
        "name": "SkillsWorkspace",
        "tag": "skills-workspace"
    },
    {
        "index": 39,
        "name": "SpringModernizationStudio",
        "tag": "spring-modernization-studio"
    },
    {
        "index": 40,
        "name": "TranslationStudio",
        "tag": "translation-studio"
    }
]
  },
  selectComponent(event) { this.setData({ activeIndex: Number(event.currentTarget.dataset.index) }); },
  setApiBaseUrl(event) { this.setData({ apiBaseUrl: event.detail.value }); }
});
