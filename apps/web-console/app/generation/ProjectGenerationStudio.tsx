"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { generationStages, generationTargets } from "../lib/catalog";
import type { GenerationCapabilityResponse, GenerationTargetId } from "../lib/contracts";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";

type GenerationDraft = {
  name: string;
  namespace: string;
  description: string;
  entity: string;
  reviewer: string;
  targets: GenerationTargetId[];
};

type WorkflowCommand = {
  id: "draft" | "approve" | "generate" | "verify";
  label: string;
  command: string;
};

const plannedAssets = [
  { icon: "code" as IconName, title: "CRUD 与健康检查", detail: "类型化接口与 OpenAPI" },
  { icon: "test" as IconName, title: "测试与构建", detail: "单元测试、CI 与 Makefile" },
  { icon: "box" as IconName, title: "容器配置", detail: "非 root Dockerfile" },
  { icon: "cloud" as IconName, title: "运行清单", detail: "Kubernetes 探针与资源" },
];

function shellQuote(value: string) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function buildWorkflowCommands(draft: GenerationDraft): WorkflowCommand[] {
  const workspace = `generated/${draft.name}`;
  return [
    {
      id: "draft",
      label: "1 · 创建草稿",
      command: `uv run elmos-project-synthesis draft --name ${shellQuote(draft.name)} --namespace ${shellQuote(draft.namespace)} --description ${shellQuote(draft.description)} --entity ${shellQuote(draft.entity)} ${draft.targets.map((target) => `--language ${target}`).join(" ")} --output synthesis-request.json`,
    },
    {
      id: "approve",
      label: "2 · 审阅并批准",
      command: `uv run elmos-project-synthesis approve --request synthesis-request.json --actor ${shellQuote(draft.reviewer)} --output approved-request.json`,
    },
    {
      id: "generate",
      label: "3 · 生成工作区",
      command: `uv run elmos-project-synthesis generate --request approved-request.json --output ${shellQuote(workspace)}`,
    },
    {
      id: "verify",
      label: "4 · 真实构建验证",
      command: `uv run elmos-project-synthesis verify --workspace ${shellQuote(workspace)} --evidence verification.json`,
    },
  ];
}

export function ProjectGenerationStudio() {
  const [name, setName] = useState("order-service");
  const [namespace, setNamespace] = useState("io.elmos.orders");
  const [description, setDescription] = useState("提供订单创建、查询与状态管理的服务");
  const [entity, setEntity] = useState("order");
  const [reviewer, setReviewer] = useState("user:reviewer");
  const [targets, setTargets] = useState<GenerationTargetId[]>(["java", "python"]);
  const [draft, setDraft] = useState<GenerationDraft | null>(null);
  const [capability, setCapability] = useState<GenerationCapabilityResponse | null>(null);
  const [feedback, setFeedback] = useState("");
  const [targetError, setTargetError] = useState("");
  const feedbackTimer = useRef<number | null>(null);

  const selectedProfiles = useMemo(
    () => generationTargets.filter((profile) => targets.includes(profile.id)),
    [targets],
  );

  const preview = draft ?? { name, namespace, description, entity, reviewer, targets };
  const previewProfiles = generationTargets.filter((profile) => preview.targets.includes(profile.id));
  const workflowCommands = buildWorkflowCommands(preview);
  const workflowScript = workflowCommands.map((item) => item.command).join("\n");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities/generation", { cache: "no-store", signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("capability unavailable")))
      .then((payload: GenerationCapabilityResponse) => setCapability(payload))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setCapability(null);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
  }, []);

  function announce(message: string) {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
    setFeedback(message);
    feedbackTimer.current = window.setTimeout(() => {
      setFeedback("");
      feedbackTimer.current = null;
    }, 4800);
  }

  function invalidateDraft() {
    setDraft(null);
  }

  function toggleTarget(id: GenerationTargetId) {
    setTargets((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setTargetError("");
    invalidateDraft();
  }

  function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (targets.length === 0) {
      setTargetError("请至少选择一个目标技术栈。");
      return;
    }
    const nextDraft = {
      name: name.trim(),
      namespace: namespace.trim(),
      description: description.trim(),
      entity: entity.trim(),
      reviewer: reviewer.trim(),
      targets,
    };
    setDraft(nextDraft);
    announce(`“${nextDraft.name}”的四阶段生成交接已就绪；仍未执行任何代码生成。`);
  }

  async function copyText(value: string, successMessage: string) {
    if (!draft) {
      announce("请先提交并锁定当前计划预览，再复制受控命令。");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      announce(successMessage);
    } catch {
      announce("浏览器未允许访问剪贴板，请手动选择并复制命令。");
    }
  }

  return (
    <div className="page-stack generation-page">
      <section className="page-header generation-header">
        <div>
          <span className="overline">PROJECT SYNTHESIS · B46–B60</span>
          <h1>多语言项目生成</h1>
          <p>用同一份项目意图规划 Java、Python 与 C# 工程；完成草稿、审批、生成和验证交接，再进入受控终端执行。</p>
        </div>
        <div className="generation-header-status"><StatusChip status={draft ? "REVIEW" : "DRAFT"} /><StatusChip status="NOT_RUN" /></div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="项目生成能力摘要">
        <article className="metric-card"><span>项目生成 Skills</span><strong>{capability?.projectSkillCount ?? 170}</strong><small>B46–B60 结构化能力</small></article>
        <article className="metric-card"><span>精确目标栈</span><strong>{capability?.targets.length ?? generationTargets.length}</strong><small>Java / Python / C#</small></article>
        <article className="metric-card"><span>已选目标</span><strong>{selectedProfiles.length}</strong><small>一个意图，多份独立工程</small></article>
        <article className="metric-card"><span>外部执行</span><strong className="metric-word warning-text">NOT_RUN</strong><small>当前页面只准备命令交接</small></article>
      </section>

      <section className="source-notice generation-notice" role="status">
        <Icon name="lock" size={16} />
        <span>{capability?.note ?? "正在读取仓库内 Project Synthesis 契约；页面不会上传内容或执行生成器。"}</span>
        <StatusChip status={capability?.source ?? "REPOSITORY_CONTRACT"} compact />
      </section>

      <div className="generation-layout">
        <form className="surface-card generation-form" onSubmit={createDraft} aria-labelledby="generation-form-title">
          <div className="generation-section-heading">
            <div><span className="overline">PROJECT INTENT</span><h2 id="generation-form-title">描述并审阅项目意图</h2></div>
            <span className="step-label">01 / 02</span>
          </div>

          <div className="generation-fields">
            <label className="generation-field"><span>项目名称</span><input value={name} onChange={(event) => { setName(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9\\-]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="project-name-hint" /><small id="project-name-hint">小写字母、数字与连字符，例如 order-service</small></label>
            <label className="generation-field"><span>命名空间</span><input value={namespace} onChange={(event) => { setNamespace(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+"} autoComplete="off" aria-describedby="namespace-hint" /><small id="namespace-hint">稳定的点分命名空间，例如 io.elmos.orders</small></label>
            <label className="generation-field generation-field-wide"><span>项目说明</span><textarea value={description} onChange={(event) => { setDescription(event.target.value); invalidateDraft(); }} required rows={4} maxLength={500} aria-describedby="description-hint" /><small id="description-hint">说明业务目标，不要粘贴凭证、生产数据或客户代码。</small></label>
            <label className="generation-field"><span>核心实体</span><input value={entity} onChange={(event) => { setEntity(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9\\-]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="entity-hint" /><small id="entity-hint">当前契约生成单实体、内存 CRUD starter。</small></label>
            <label className="generation-field"><span>审批者标识</span><input value={reviewer} onChange={(event) => { setReviewer(event.target.value); invalidateDraft(); }} required pattern={"[a-zA-Z0-9][a-zA-Z0-9._:@/\\-]{2,199}"} autoComplete="off" aria-describedby="reviewer-hint" /><small id="reviewer-hint">写入批准摘要，例如 user:reviewer；不填写密钥或邮箱凭证。</small></label>
          </div>

          <fieldset className="target-fieldset" aria-describedby="target-hint target-error">
            <legend><span><span className="overline">EXACT TARGETS</span><strong>选择目标技术栈</strong></span><span className="step-label">02 / 02</span></legend>
            <p id="target-hint">每个选项都是版本锁定的完整目标配置，可同时选择。</p>
            <div className="target-grid">
              {generationTargets.map((profile) => {
                const checked = targets.includes(profile.id);
                return (
                  <label className={`target-card target-${profile.accent} ${checked ? "selected" : ""}`} key={profile.id}>
                    <input type="checkbox" checked={checked} onChange={() => toggleTarget(profile.id)} />
                    <span className="target-check"><Icon name="check" size={13} /></span>
                    <span className="target-icon"><Icon name={profile.icon} size={21} /></span>
                    <span className="target-copy"><strong>{profile.language} {profile.runtime}</strong><small>{profile.framework}</small><em>默认端口 {profile.port}</em></span>
                  </label>
                );
              })}
            </div>
            <span className="field-error" id="target-error" role="alert">{targetError}</span>
          </fieldset>

          <div className="planned-assets" aria-labelledby="assets-title">
            <div className="generation-section-heading compact"><div><span className="overline">PLANNED ASSETS</span><h3 id="assets-title">生成计划包含</h3></div><span>实际未生成</span></div>
            <div className="asset-grid">{plannedAssets.map((asset) => <div className="asset-item" key={asset.title}><span><Icon name={asset.icon} size={17} /></span><div><strong>{asset.title}</strong><small>{asset.detail}</small></div></div>)}</div>
          </div>

          <div className="generation-submit-row">
            <div><Icon name="lock" size={16} /><span><strong>本页只锁定交接预览</strong><small>批准摘要仍由 CLI 在受控终端生成</small></span></div>
            <button className="button button-primary" type="submit"><Icon name="spark" size={16} />准备完整生成交接</button>
          </div>
        </form>

        <aside className="generation-preview" aria-label="生成计划预览">
          <div className="generation-preview-hero">
            <div className="preview-status-row"><span className="overline">GOVERNED PLAN PREVIEW</span><StatusChip status={draft ? "REVIEW" : "DRAFT"} compact /></div>
            <span className="preview-project-icon"><Icon name="repository" size={24} /></span>
            <h2>{preview.name || "未命名项目"}</h2>
            <p>{preview.description || "填写项目说明后，这里会显示生成计划摘要。"}</p>
            <div className="preview-tags"><span>{preview.entity || "未指定实体"}</span><span>{preview.namespace || "未指定命名空间"}</span><span>{preview.reviewer || "未指定审批者"}</span></div>
          </div>

          <div className="preview-section">
            <div className="preview-section-title"><span>目标输出</span><b>{previewProfiles.length}</b></div>
            <div className="preview-target-list">
              {previewProfiles.map((profile) => <div key={profile.id}><span className={`mini-target target-${profile.accent}`}><Icon name={profile.icon} size={15} /></span><span><strong>{profile.language} {profile.runtime}</strong><small>{profile.framework}</small></span><em>:{profile.port}</em></div>)}
              {previewProfiles.length === 0 && <p className="preview-empty">尚未选择目标技术栈。</p>}
            </div>
          </div>

          <div className="preview-section pipeline-section">
            <div className="preview-section-title"><span>受控生成阶段</span><b>{generationStages.length}</b></div>
            <ol className="generation-pipeline">
              {generationStages.map((phase, index) => <li key={phase.batch}><i>{index + 1}</i><span><strong>{phase.title}</strong><small>{phase.batch} · {phase.detail}</small></span></li>)}
            </ol>
          </div>

          <div className="preview-command">
            <div><span>完整 CLI 交接</span><button type="button" disabled={!draft} onClick={() => copyText(workflowScript, "四阶段 CLI 命令已复制，请在项目合成引擎目录中依次执行。")}><Icon name="copy" size={13} />复制全部</button></div>
            <ol className="workflow-command-list">
              {workflowCommands.map((item) => (
                <li className="workflow-command-item" key={item.id}>
                  <div><strong>{item.label}</strong><button type="button" disabled={!draft} aria-label={`复制${item.label}命令`} onClick={() => copyText(item.command, `${item.label}命令已复制。`)}><Icon name="copy" size={12} />复制</button></div>
                  <code>{item.command}</code>
                </li>
              ))}
            </ol>
            <small>{draft ? "命令与 Project Synthesis 1.0.0 CLI 完全对应；按顺序执行，任何一步失败都应停止。" : "先提交有效表单以锁定命令，防止复制仍在变化的未审阅输入。"}</small>
          </div>

          <div className="generation-boundary">
            <Icon name="shield" size={19} />
            <div><strong>证据边界保持关闭</strong><small>持久化数据库、身份与租户、云部署、SLO、DR 及独立验证均不在当前 starter 证明范围内。</small></div>
            <StatusChip status="NOT_CERTIFIED" compact />
          </div>
        </aside>
      </div>

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true"><span><Icon name="check" size={17} /></span>{feedback}</div>
    </div>
  );
}
