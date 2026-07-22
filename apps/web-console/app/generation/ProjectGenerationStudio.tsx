"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";

type TargetId = "java" | "python" | "csharp";

type TargetProfile = {
  id: TargetId;
  language: string;
  runtime: string;
  framework: string;
  port: number;
  accent: "amber" | "blue" | "violet";
  icon: IconName;
};

type GenerationDraft = {
  name: string;
  namespace: string;
  description: string;
  entity: string;
  targets: TargetId[];
};

const targetProfiles: TargetProfile[] = [
  { id: "java", language: "Java", runtime: "21", framework: "Spring Boot 3.5.3", port: 8081, accent: "amber", icon: "code" },
  { id: "python", language: "Python", runtime: "3.12", framework: "FastAPI 0.116.1", port: 8082, accent: "blue", icon: "spark" },
  { id: "csharp", language: "C#", runtime: ".NET 10", framework: "ASP.NET Core", port: 8083, accent: "violet", icon: "layers" },
];

const phases = [
  { batch: "B46–B48", title: "需求发现", detail: "澄清实体、需求与验收条件" },
  { batch: "B49–B50", title: "架构约束", detail: "冻结运行时与框架版本" },
  { batch: "B51–B52", title: "工程蓝图", detail: "规划 API、测试和配置" },
  { batch: "B53–B57", title: "多语言发射", detail: "按所选目标生成独立项目" },
  { batch: "B58–B60", title: "验证与交付", detail: "构建、探针与证据归档" },
];

const plannedAssets = [
  { icon: "code" as IconName, title: "CRUD 与健康检查", detail: "类型化接口与 OpenAPI" },
  { icon: "test" as IconName, title: "测试与构建", detail: "单元测试、CI 与 Makefile" },
  { icon: "box" as IconName, title: "容器配置", detail: "非 root Dockerfile" },
  { icon: "cloud" as IconName, title: "运行清单", detail: "Kubernetes 探针与资源" },
];

function shellQuote(value: string) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

export function ProjectGenerationStudio() {
  const [name, setName] = useState("order-service");
  const [namespace, setNamespace] = useState("io.elmos.orders");
  const [description, setDescription] = useState("提供订单创建、查询与状态管理的服务");
  const [entity, setEntity] = useState("order");
  const [targets, setTargets] = useState<TargetId[]>(["java", "python"]);
  const [draft, setDraft] = useState<GenerationDraft | null>(null);
  const [feedback, setFeedback] = useState("");
  const [targetError, setTargetError] = useState("");
  const feedbackTimer = useRef<number | null>(null);

  const selectedProfiles = useMemo(
    () => targetProfiles.filter((profile) => targets.includes(profile.id)),
    [targets],
  );

  const preview = draft ?? { name, namespace, description, entity, targets };
  const previewProfiles = targetProfiles.filter((profile) => preview.targets.includes(profile.id));
  const command = `elmos-project-synthesis draft --name ${shellQuote(preview.name || "project-name")} --namespace ${shellQuote(preview.namespace || "com.example.project")} --description ${shellQuote(preview.description || "project description")} --entity ${shellQuote(preview.entity || "entity")} ${preview.targets.map((target) => `--language ${target}`).join(" ")} --output synthesis-request.json`;

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

  function toggleTarget(id: TargetId) {
    setTargets((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setTargetError("");
    setDraft(null);
  }

  function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (targets.length === 0) {
      setTargetError("请至少选择一个目标技术栈。");
      return;
    }
    const nextDraft = { name: name.trim(), namespace: namespace.trim(), description: description.trim(), entity: entity.trim(), targets };
    setDraft(nextDraft);
    announce(`“${nextDraft.name}”的生成计划已保存为当前页面草稿；未执行任何代码生成。`);
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(command);
      announce("CLI 草稿命令已复制，可在受控终端中执行。");
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
          <p>用同一份项目意图规划 Java、Python 与 C# 工程；先看清目标、资产和验证边界，再交给受控生成流程。</p>
        </div>
        <div className="generation-header-status"><StatusChip status="DRAFT" /><StatusChip status="NOT_RUN" /></div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="项目生成能力摘要">
        <article className="metric-card"><span>项目生成 Skills</span><strong>170</strong><small>B46–B60 结构化能力</small></article>
        <article className="metric-card"><span>精确目标栈</span><strong>3</strong><small>Java / Python / C#</small></article>
        <article className="metric-card"><span>已选目标</span><strong>{selectedProfiles.length}</strong><small>一个意图，多份独立工程</small></article>
        <article className="metric-card"><span>外部执行</span><strong className="metric-word warning-text">NOT_RUN</strong><small>当前页面仅保存内存草稿</small></article>
      </section>

      <section className="source-notice generation-notice" role="status">
        <Icon name="lock" size={16} />
        <span>能力来自仓库内 Project Synthesis 1.0.0 契约；目标版本不可任意组合，实际生成、构建与认证均未运行。</span>
        <StatusChip status="REPOSITORY_CONTRACT" compact />
      </section>

      <div className="generation-layout">
        <form className="surface-card generation-form" onSubmit={createDraft} aria-labelledby="generation-form-title">
          <div className="generation-section-heading">
            <div><span className="overline">PROJECT INTENT</span><h2 id="generation-form-title">描述你要生成的项目</h2></div>
            <span className="step-label">01 / 02</span>
          </div>

          <div className="generation-fields">
            <label className="generation-field"><span>项目名称</span><input value={name} onChange={(event) => { setName(event.target.value); setDraft(null); }} required pattern={"[a-z][a-z0-9\\-]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="project-name-hint" /><small id="project-name-hint">小写字母、数字与连字符，例如 order-service</small></label>
            <label className="generation-field"><span>命名空间</span><input value={namespace} onChange={(event) => { setNamespace(event.target.value); setDraft(null); }} required pattern={"[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+"} autoComplete="off" aria-describedby="namespace-hint" /><small id="namespace-hint">稳定的点分命名空间，例如 io.elmos.orders</small></label>
            <label className="generation-field generation-field-wide"><span>项目说明</span><textarea value={description} onChange={(event) => { setDescription(event.target.value); setDraft(null); }} required rows={4} maxLength={500} aria-describedby="description-hint" /><small id="description-hint">说明业务目标，不要粘贴凭证、生产数据或客户代码。</small></label>
            <label className="generation-field generation-field-wide"><span>核心实体</span><input value={entity} onChange={(event) => { setEntity(event.target.value); setDraft(null); }} required pattern={"[a-z][a-z0-9\\-]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="entity-hint" /><small id="entity-hint">当前契约生成单实体、内存 CRUD starter；持久化与身份能力不在此范围。</small></label>
          </div>

          <fieldset className="target-fieldset" aria-describedby="target-hint target-error">
            <legend><span><span className="overline">EXACT TARGETS</span><strong>选择目标技术栈</strong></span><span className="step-label">02 / 02</span></legend>
            <p id="target-hint">每个选项都是版本锁定的完整目标配置，可同时选择。</p>
            <div className="target-grid">
              {targetProfiles.map((profile) => {
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
            <div><Icon name="lock" size={16} /><span><strong>仅保存当前页面草稿</strong><small>不会上传、审批或运行生成器</small></span></div>
            <button className="button button-primary" type="submit"><Icon name="spark" size={16} />生成计划预览</button>
          </div>
        </form>

        <aside className="generation-preview" aria-label="生成计划预览">
          <div className="generation-preview-hero">
            <div className="preview-status-row"><span className="overline">LIVE PLAN PREVIEW</span><StatusChip status={draft ? "DRAFT" : "REVIEW"} compact /></div>
            <span className="preview-project-icon"><Icon name="repository" size={24} /></span>
            <h2>{preview.name || "未命名项目"}</h2>
            <p>{preview.description || "填写项目说明后，这里会显示生成计划摘要。"}</p>
            <div className="preview-tags"><span>{preview.entity || "未指定实体"}</span><span>{preview.namespace || "未指定命名空间"}</span></div>
          </div>

          <div className="preview-section">
            <div className="preview-section-title"><span>目标输出</span><b>{previewProfiles.length}</b></div>
            <div className="preview-target-list">
              {previewProfiles.map((profile) => <div key={profile.id}><span className={`mini-target target-${profile.accent}`}><Icon name={profile.icon} size={15} /></span><span><strong>{profile.language} {profile.runtime}</strong><small>{profile.framework}</small></span><em>:{profile.port}</em></div>)}
              {previewProfiles.length === 0 && <p className="preview-empty">尚未选择目标技术栈。</p>}
            </div>
          </div>

          <div className="preview-section pipeline-section">
            <div className="preview-section-title"><span>受控生成阶段</span><b>5</b></div>
            <ol className="generation-pipeline">
              {phases.map((phase, index) => <li key={phase.batch}><i>{index + 1}</i><span><strong>{phase.title}</strong><small>{phase.batch} · {phase.detail}</small></span></li>)}
            </ol>
          </div>

          <div className="preview-command">
            <div><span>CLI 草稿参考</span><button type="button" onClick={copyCommand}><Icon name="copy" size={13} />复制命令</button></div>
            <code>{command}</code>
            <small>命名空间、目标语言与端口和 Project Synthesis 1.0.0 引擎保持一致；此界面不会执行命令。</small>
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
