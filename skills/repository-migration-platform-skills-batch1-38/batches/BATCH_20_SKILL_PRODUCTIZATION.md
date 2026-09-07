# Batch 20：Skill SDK、Runtime、Registry与产品化封装

## Goal

把全部能力封装为有Schema、权限、Sandbox、版本、签名、计量、License和认证的Skill生态。

## Inputs

- Platform capabilities；
- Runtime/tool/model contracts；
- Registry policies；
- Commercial terms；

## Outputs

- Skill manifests/SDKs/runtime；
- Plugin runtime；
- Registry/Marketplace；
- CLI/API/IDE/Web；
- Metering/billing；
- SC1–SC5；

## Execution Flow

1. 盘点能力并划分Skill边界；
2. 生成Input/Output/Capability contracts；
3. 构建Package/SBOM/Signature；
4. 安装与依赖解析；
5. Sandbox执行与Effect治理；
6. Registry/Marketplace发布；
7. 持续认证和撤销；

## Verification

- Skill不可自由文本隐式要权限；
- Revoked Skill不可执行；
- 计量不可由Skill篡改；
- 商业排序不影响认证；

## Stop Conditions

- 未声明网络/Secret/Effect；
- Plugin继承宿主权限；
- 自我认证；

## Gate

`SC1–SC5`

## Installable Skill

`agent-skills/runtime/b20-skill-productization/SKILL.md`
