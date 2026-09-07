# PostgreSQL 生产角色与函数 Owner

`V080` 对租户表启用 `FORCE ROW LEVEL SECURITY`。因此高价值 `SECURITY DEFINER` 函数不能长期由普通登录型 Flyway 用户拥有。

生产环境必须在 Migration 后执行一次 DBA 管理的角色硬化：

```text
elmos_schema_owner       NOLOGIN, owns schemas/tables/helper functions, no BYPASSRLS
elmos_runtime_definer    NOLOGIN, BYPASSRLS, owns only vetted SECURITY DEFINER functions
elmos_control_api        NOLOGIN group role
elmos_scheduler          NOLOGIN group role
elmos_runtime_gateway    NOLOGIN group role
elmos_verifier           NOLOGIN group role
elmos_deployment_gate    NOLOGIN group role
```

登录凭据对应的实际 Login Role 只加入一个或少数 Group Role，不直接成为对象 Owner。

## 为什么 runtime definer 需要 BYPASSRLS

- 表采用 `FORCE RLS`，连表 Owner 也受策略约束；
- Claim/P05 等函数接受显式 `tenant_id`，并在函数内重新验证 Tenant、Run、Lease、Fence 和 Revision；
- 若函数 Owner 没有 BYPASSRLS，调用者忘记或无法设置 `app.tenant_id` 时会得到不可预测的空结果；
- 受控 `NOLOGIN + BYPASSRLS` Owner 只拥有已审计函数，服务账号只有 EXECUTE，既避免 RLS 递归问题，也不把绕过能力交给应用连接。

该 Owner 的风险必须通过以下措施收敛：

1. `NOLOGIN`；
2. 只拥有 vetted functions，不拥有任意动态 SQL 函数；
3. 固定 `search_path`；
4. 所有对象 Schema-qualified；
5. `REVOKE ALL ... FROM PUBLIC`；
6. 服务按职责只获得指定函数 EXECUTE；
7. 函数变更需要数据库安全 Review；
8. CI 检查所有 SECURITY DEFINER 都已撤销 PUBLIC；
9. 审计函数 Owner、ACL 和 Hash；
10. 不把 runtime definer 角色授予任何 Login Role。

## 执行

`roles-and-grants.example.sql` 需要集群管理员执行。它使用固定示例角色名，企业部署可按命名规范修改。

```bash
psql "$ELMOS_ADMIN_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -f database/roles/roles-and-grants.example.sql
```

后续 Flyway 登录角色应只获得 `elmos_schema_owner` 成员资格，并在 Migration 连接中显式 `SET ROLE elmos_schema_owner`；不要让长期应用连接继承该角色。

执行后检查：

```sql
SELECT n.nspname, p.proname, r.rolname AS owner, r.rolcanlogin, r.rolbypassrls,
       has_function_privilege('public', p.oid, 'execute') AS public_execute
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_roles r ON r.oid = p.proowner
WHERE p.prosecdef
  AND n.nspname IN ('core','exec','integration','verify','ops')
ORDER BY 1,2;
```

期望：Owner 为 `elmos_runtime_definer`、`rolcanlogin=false`、`rolbypassrls=true`、`public_execute=false`。
