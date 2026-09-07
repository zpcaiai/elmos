"use client";

import { useState } from "react";
import { SmokeRunButton } from "../components/SmokeRunButton";

const projectRefPattern = /^[a-z0-9][a-z0-9._/-]{2,180}$/i;

export function SmokeConsole() {
  const [draft, setDraft] = useState("");
  const [projectRef, setProjectRef] = useState<string | null>(null);
  const valid = projectRefPattern.test(draft.trim()) && !draft.includes("..");

  return (
    <div className="content-shell">
      <header className="business-hero">
        <h1>一键冒烟运行</h1>
        <p>
          生成或转换完成的项目会自带 Batch 46 冒烟包。在这里选中项目即可一键跑起来：
          自动灌入一次性种子数据、探活、跑冒烟断言，免费额度到期后自动停止服务并清空临时数据。
        </p>
      </header>

      <section className="business-form">
        <label className="business-form-grid">
          <span>项目引用（相对 ELMOS_SMOKE_PROJECTS_ROOT 的路径）</span>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="例如 java-to-python/orders-service"
            maxLength={180}
          />
        </label>
        <div className="business-actions">
          <button
            type="button"
            className="button button-primary"
            onClick={() => setProjectRef(draft.trim())}
            disabled={!valid}
          >
            载入冒烟包
          </button>
        </div>
      </section>

      {projectRef ? <SmokeRunButton key={projectRef} projectRef={projectRef} /> : null}
    </div>
  );
}
