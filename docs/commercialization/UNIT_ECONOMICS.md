# 单位经济性核算（D-04）

生成日期：2026-07-28
关联：定价目录 `costValidationStatus = NOT_RUN`
工具：`scripts/commercial/unit_economics.py`

---

## 1. 为什么这件事排在最前面

定价目录声明：¥129/月含 **2,000 万 token + 600 Credit**，年付 ¥1,290 含每月
**2,500 万 token + 750 Credit**。但 `costValidationStatus` 一直是 `NOT_RUN`
——**没人知道一单是赚是亏**。

D-01（大陆主体）与 D-03（SaaS 自助订阅）让这件事更紧迫：

- 自助订阅**无法逐单审批**。定价一旦上线，来的就是真实用量，亏也得认。
- 大陆 B2C 场景下调价与退款走公开渠道，改价的舆情成本远高于 B 端合同续签。
- 额度是**按月发放**的，亏损会随订阅数线性放大，不是一次性损失。

这项核算不需要写代码，也不依赖任何外部审批——**今天就能做完**。

---

## 2. 工具怎么用

```bash
# 生成待填模板
python3 scripts/commercial/unit_economics.py --template > my-costs.json

# 填完后核算
python3 scripts/commercial/unit_economics.py --inputs my-costs.json
```

退出码：`0` 全部付费套餐毛利为正；`3` 存在负毛利或输入不全；`2` 输入非法。

**工具不发明任何单价。** 任一必填输入为 `null` 就输出 `BLOCKED`，
不会用"行业经验值"替代：

```
DECISION=BLOCKED
  以下输入尚未取得真实报价，拒绝输出毛利：
    - modelInputPricePerMillionFen（模型输入 token 单价（分 / 百万 token））
    ...
  说明：用假设值算出的毛利看起来像结论，比不算更危险。
        costValidationStatus 保持 NOT_RUN。
```

---

## 3. 需要你填的 16 项

| 分类 | 字段 | 从哪里拿 |
|---|---|---|
| 模型 | `modelInputPricePerMillionFen` | 模型供应商价目表 |
| | `modelOutputPricePerMillionFen` | 同上 |
| | `modelCacheReadPricePerMillionFen` | 同上 |
| | `modelCacheWritePricePerMillionFen` | 同上 |
| 用量结构 | `outputTokenShare` / `cacheReadShare` / `cacheWriteShare` | **现有真实调用日志**，不要拍脑袋 |
| 执行面 | `runnerCostPerCreditFen` | 云主机时价 ÷ 单位时间可完成的 Credit 数 |
| 存储 | `storageCostPerGbMonthFen`、`storageGbPerActiveProject` | 对象存储价目 + 实际产物体积抽样 |
| 出网 | `egressCostPerGbFen`、`egressGbPerMonthPerAccount` | 云厂商价目 + 下载量估计 |
| 支持 | `supportCostPerAccountMonthFen` | 人力成本 ÷ 预期账户数 |
| 支付 | `paymentFeeRate` | 支付宝/微信费率（通常 0.006） |
| 税 | `taxRate` | 财务确认；标价含税时用于倒算净收入 |
| 假设 | `utilization` | 额度实际使用率；**先按 1.0 看最坏情况** |

**`outputTokenShare` 这三项占比最容易被低估。** 输出 token 通常比输入贵 5 倍，
占比估错 10 个百分点，结论可能直接反转。有真实调用日志就用日志。

---

## 4. 输出解读

工具给两类结果：

**逐套餐成本拆解** —— 模型 / Runner / 存储 / 出网 / 支持 / 通道费，
以及净收入与贡献毛利。

**盈亏平衡使用率** —— 二分求出毛利归零的那个使用率。这是最有决策价值的数字：

```
elmos-pro-monthly: 0.5404（约 1080 万 token）
```

意思是：**用户用掉 54% 额度就开始亏**。那么真正要问的问题不是"毛利多少"，
而是"实际用户会用掉多少"。

结果分三种，处置方式不同：

| 平衡点 | 含义 | 该做什么 |
|---|---|---|
| > 1.0 | 用满额度也不亏 | 定价安全，可以上线 |
| 0.4 – 1.0 | 重度用户会亏 | 看真实使用率分布；重度用户占比高就得调额度或加档 |
| < 0.4 | 大部分用户都会亏 | **必须先改定价或额度**，不要带着这个数字上线 |
| 0 | 零使用即亏 | 固定成本已超净收入，商业模型不成立 |

免费体验的负数**不是亏损，是获客成本**。工具会单独标注。
要看的是"转化率 × 付费期毛利"能否覆盖它。

---

## 5. 一个演示（不是结论）

用一组示例数字（模型输入 ¥3/百万、输出 ¥15/百万、输出占比 20%、
Runner ¥0.20/Credit、通道费 0.6%、税率 6%）跑出来：

```
DECISION=MARGIN_NEGATIVE   utilization=1.0
  elmos-pro-monthly  ✗ 亏损
    净收入 ¥121.70   模型 ¥92.55  Runner ¥120.00  ...  贡献毛利 ¥-97.69
  盈亏平衡使用率：elmos-pro-monthly 0.5404 / elmos-pro-annual 0.3550
```

**这组数字未经任何报价核实，只用于验证计算逻辑，不构成对现有定价的判断。**
但它展示了一件事：在这个量级下，**Runner 机时成本很可能和模型成本同一量级甚至更高**，
而定价讨论里通常只盯着 token。`runnerCostPerCreditFen` 值得单独花时间测准。

---

## 6. 什么时候才能把 `costValidationStatus` 改成 `VALIDATED`

四个条件同时满足：

1. 16 项输入**每一项**都能追溯到真实报价单、账单或抽样测量，来源写进核算记录
2. 在 `utilization=1.0`（最坏情况）下跑过一次，结果被明确接受或据此调过价
3. 用量结构占比来自**真实调用日志**，不是估计
4. 核算记录归档，与目录版本号绑定；后续调价必须重跑

改完之后，发布门禁会认这一项：

```bash
python3 scripts/commercial/validate_pricing_catalog_publication.py --check-publishable \
  --commercial-evidence <含 icpFiling 与 invoiceCapability 的证据文件>
```

**本工具的输出是计算，不是证据。** 它能告诉你数字对不对，
不能替你证明输入是真的。
