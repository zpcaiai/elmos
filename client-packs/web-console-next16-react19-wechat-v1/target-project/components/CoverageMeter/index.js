const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "CoverageMeter",
  "title": "0 / 0；当前没有可执行义务",
  "role": "chart",
  "source": {
    "file": "app/components/ProjectEvidenceCharts.tsx",
    "componentName": "CoverageMeter",
    "sha256": "sha256:1191ba4343eba89806266218465287a1169f436b763c4214b2a4dfd897e741db",
    "range": {
      "start": 1873,
      "end": 4313
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE",
    "reason": "spread attributes are outside certified-component-v1",
    "category": "platform-semantics"
  },
  "props": [
    {
      "name": "counts",
      "type": "StatusCounts",
      "optional": true
    },
    {
      "name": "label",
      "type": "string",
      "optional": false
    },
    {
      "name": "passed",
      "type": "number",
      "optional": false
    },
    {
      "name": "status",
      "type": "DisplayStatus",
      "optional": false
    },
    {
      "name": "total",
      "type": "number",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "0 / 0；当前没有可执行义务",
    "NOT_RUN",
    "PASSED",
    "UNKNOWN",
    "aria-valuemax",
    "aria-valuemin",
    "aria-valuenow",
    "aria-valuetext",
    "evidence-meter",
    "evidence-meter-heading",
    "evidence-meter-legend",
    "evidence-meter-track",
    "progressbar",
    "status",
    "true"
  ],
  "adapters": [
    "wechat-plain-collection-projection-v1"
  ],
  "obligations": [
    "CoverageMeter:source-blocker"
  ],
  "irDigest": "sha256:c19dbf8b731734078536d6485224d0e36438129e99dd1436ca9fa6185dd334c5"
}));
