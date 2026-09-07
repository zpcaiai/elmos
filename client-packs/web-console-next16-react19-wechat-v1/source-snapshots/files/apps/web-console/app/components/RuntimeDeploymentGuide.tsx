import type { DeploymentGuidance, GenerationTargetId } from "../lib/contracts";
import { Icon } from "./Icon";
import { StatusChip } from "./StatusChip";

type RuntimeDeploymentGuideProps = {
  guidance: DeploymentGuidance;
  selectedTargets?: GenerationTargetId[];
  id: string;
};

function hardware(cpu: number, memoryGb: number, diskGb: number) {
  return `${cpu} vCPU · ${memoryGb} GB RAM · ${diskGb} GB 磁盘`;
}

export function RuntimeDeploymentGuide({ guidance, selectedTargets, id }: RuntimeDeploymentGuideProps) {
  const profiles = guidance.localProfiles.filter((profile) => (
    !selectedTargets || profile.id === "spring-modernization"
      || selectedTargets.includes(profile.id as GenerationTargetId)
  ));
  const sequential = {
    cpu: Math.max(...profiles.map((profile) => profile.recommended.cpu)),
    memoryGb: Math.max(...profiles.map((profile) => profile.recommended.memoryGb)),
    diskGb: profiles.reduce((total, profile) => total + profile.recommended.diskGb, 0),
  };
  const concurrent = {
    cpu: profiles.reduce((total, profile) => total + profile.recommended.cpu, 0),
    memoryGb: profiles.reduce((total, profile) => total + profile.recommended.memoryGb, 0),
    diskGb: profiles.reduce((total, profile) => total + profile.recommended.diskGb, 0),
  };

  return (
    <section className="surface-card runtime-deployment-guide" aria-labelledby={`${id}-title`}>
      <div className="runtime-guide-heading">
        <div>
          <span className="overline">LOCAL RUN · CLOUD HANDOFF</span>
          <h2 id={`${id}-title`}>本地运行与云部署</h2>
          <p>下载结果内同步生成本地步骤、平台选择和 Cloud Run 配置；外部执行不会被页面假定为成功。</p>
        </div>
        <div className="runtime-guide-status">
          <StatusChip status={guidance.status} compact />
          <StatusChip status={guidance.externalEvidence} compact />
        </div>
      </div>

      <div className="runtime-guide-summary">
        <article>
          <span className="runtime-guide-icon"><Icon name="server" size={18} /></span>
          <div><small>逐个构建 / 运行推荐</small><strong>{hardware(sequential.cpu, sequential.memoryGb, sequential.diskGb)}</strong><span>磁盘包含全部已选工程与依赖缓存</span></div>
        </article>
        <article>
          <span className="runtime-guide-icon"><Icon name="layers" size={18} /></span>
          <div><small>全部目标并发推荐</small><strong>{hardware(concurrent.cpu, concurrent.memoryGb, concurrent.diskGb)}</strong><span>按同时构建并运行的保守合计</span></div>
        </article>
        <article className="runtime-guide-recommended">
          <span className="runtime-guide-icon"><Icon name="cloud" size={18} /></span>
          <div><small>推荐云平台</small><strong>{guidance.recommendation.platform}</strong><span>私有默认 · 镜像摘要 · 最小权限</span></div>
        </article>
      </div>

      <div className="runtime-profile-grid">
        {profiles.map((profile) => (
          <details key={profile.id} className="runtime-profile">
            <summary>
              <span><strong>{profile.label}</strong><small>{profile.framework}</small></span>
              <span className="runtime-profile-port">:{profile.port}</span>
              <Icon name="chevron" size={15} />
            </summary>
            <div className="runtime-profile-body">
              <dl>
                <div><dt>精确工具链</dt><dd>{profile.toolchain}</dd></div>
                <div><dt>最低硬件</dt><dd>{hardware(profile.minimum.cpu, profile.minimum.memoryGb, profile.minimum.diskGb)}</dd></div>
                <div><dt>推荐硬件</dt><dd>{hardware(profile.recommended.cpu, profile.recommended.memoryGb, profile.recommended.diskGb)}</dd></div>
                <div><dt>范围</dt><dd>{profile.scope}</dd></div>
              </dl>
              <div className="runtime-command-grid">
                <div><strong>验证</strong><pre>{profile.verifyCommands.join("\n")}</pre></div>
                <div><strong>运行与健康</strong><pre>{profile.runCommands.join("\n")}</pre></div>
              </div>
            </div>
          </details>
        ))}
      </div>

      <div className="cloud-option-grid" aria-label="可选云部署平台">
        {guidance.cloudOptions.map((option) => (
          <article key={option.id} className={option.status === "RECOMMENDED" ? "cloud-option-recommended" : ""}>
            <div><strong>{option.name}</strong><StatusChip status={option.status} compact /></div>
            <p>{option.fit}</p>
            <small>{option.tradeoff}</small>
          </article>
        ))}
      </div>

      <details className="cloud-run-details">
        <summary>
          <span><Icon name="cloud" size={17} /><strong>展开 Google Cloud Run 详细配置与步骤</strong></span>
          <Icon name="chevron" size={16} />
        </summary>
        <div className="cloud-run-detail-body">
          <p>{guidance.recommendation.reason}</p>
          <div className="cloud-run-detail-grid">
            <div>
              <h3>部署前必须补齐</h3>
              <ul>{guidance.recommendation.requiredInputs.map((input) => <li key={input}>{input}</li>)}</ul>
            </div>
            <div>
              <h3>回滚与清理</h3>
              <ul>{[...guidance.recommendation.rollback, ...guidance.recommendation.cleanup].map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
          <ol className="cloud-run-steps">
            {guidance.recommendation.steps.map((step) => (
              <li key={step.title}>
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
                {step.commands && <pre>{step.commands.join("\n")}</pre>}
              </li>
            ))}
          </ol>
          <div className="runtime-guide-links">
            {guidance.recommendation.officialDocs.map((doc) => (
              <a key={doc.url} href={doc.url} target="_blank" rel="noreferrer">
                {doc.label}<Icon name="external" size={13} />
              </a>
            ))}
          </div>
          <div className="runtime-guide-boundary">
            <Icon name="lock" size={17} />
            <span><strong>外部执行仍为 NOT_RUN</strong><small>只有真实账号、精确配置、镜像摘要、运行证据和独立验收齐备后，才能更新部署状态。</small></span>
          </div>
        </div>
      </details>
    </section>
  );
}
