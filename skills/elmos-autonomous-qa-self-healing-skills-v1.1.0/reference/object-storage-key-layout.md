# Object Storage Key Layout

推荐键：

```text
{tenant_id}/{project_id}/{revision_id}/blobs/{sha256[0:2]}/{sha256}
{tenant_id}/{project_id}/{revision_id}/manifests/{output_id}/project-output-manifest.json
{tenant_id}/{project_id}/{revision_id}/bundles/{bundle_id}/{filename}
{tenant_id}/{project_id}/{revision_id}/tmp/{run_id}/{upload-id}
```

规则：

- Blob 使用内容寻址并通过数据库引用计数去重。
- `tmp` 对象不可对用户可见；完成哈希、Secrets、路径和租户校验后才 Promote。
- 认证产出开启版本控制/对象锁；更新通过新 revision，不原地覆盖。
- 下载使用短期签名 URL，服务端校验租户和项目权限。
- 垃圾回收只删除无数据库引用、非 legal hold 且超过保留期的 Blob。
