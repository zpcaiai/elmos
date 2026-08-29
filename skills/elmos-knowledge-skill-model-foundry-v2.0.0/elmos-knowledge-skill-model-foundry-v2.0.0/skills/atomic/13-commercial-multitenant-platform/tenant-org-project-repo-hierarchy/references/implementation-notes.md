# Implementation Notes

- Skill ID: `tenant-org-project-repo-hierarchy`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 管理组织、租户、工作区、项目、仓库、分支、环境和成员关系。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
