const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "RuntimeDeploymentGuide",
  "title": "LOCAL RUN · CLOUD HANDOFF",
  "role": "disclosure",
  "source": {
    "file": "app/components/RuntimeDeploymentGuide.tsx",
    "componentName": "RuntimeDeploymentGuide",
    "sha256": "sha256:2982aa717205f11ffed88ddc53f5f62ecedf9bf3f1575e4f47455c2daa5a784b",
    "range": {
      "start": 417,
      "end": 6145
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TAG",
    "reason": "tag \"details\" is outside certified-component-v1",
    "category": "platform-semantics"
  },
  "props": [
    {
      "name": "guidance",
      "type": "RuntimeDeploymentGuideProps",
      "optional": false
    },
    {
      "name": "id",
      "type": "RuntimeDeploymentGuideProps",
      "optional": false
    },
    {
      "name": "selectedTargets",
      "type": "RuntimeDeploymentGuideProps",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "LOCAL RUN · CLOUD HANDOFF",
    "RECOMMENDED",
    "_blank",
    "chevron",
    "cloud",
    "cloud-option-grid",
    "cloud-option-recommended",
    "cloud-run-detail-body",
    "cloud-run-detail-grid",
    "cloud-run-details",
    "cloud-run-steps",
    "external",
    "layers",
    "lock",
    "noreferrer",
    "overline",
    "runtime-command-grid",
    "runtime-guide-boundary",
    "runtime-guide-heading",
    "runtime-guide-icon",
    "runtime-guide-links",
    "runtime-guide-recommended",
    "runtime-guide-status",
    "runtime-guide-summary"
  ],
  "adapters": [
    "wechat-controlled-disclosure-v1",
    "wechat-plain-collection-projection-v1"
  ],
  "obligations": [
    "RuntimeDeploymentGuide:source-blocker"
  ],
  "irDigest": "sha256:fe96224fd474cb784eadef000584e27188e5633c1b5e4d70faadf18e9d666fe6"
}));
