# 实现详解 / Implementation Guide (Bilingual 中英双语)

> 本文档面向想深入理解本项目技术细节的读者。每节先中文后英文。
> This doc is for readers who want deep technical detail. Each section
> presents Chinese first, then English.

---

## 1. 项目定位 / Project Positioning

**中文：** 本项目是一个合成数据案例研究，模拟食品工厂中"采购导出用供应商编号、仓库用内部 SKU、报表按产品层级汇总"导致的收货数量对齐问题。核心不是做报表，而是展示**主数据差异调查能力**：定位差异、保留原始记录、把待确认项交给负责人，而不是猜测后改平。

**English:** A synthetic case study simulating a food factory where purchasing exports use supplier item codes, the warehouse uses internal SKUs, and reports roll up by product hierarchy. The core deliverable is not a dashboard but a demonstration of **master-data investigation capability**: locate discrepancies, preserve source records, and route uncertain items to named owners instead of guessing.

---

## 2. 数据模型设计 / Data Model Design

**中文：** 五张表形成一条证据链：

- `products.csv` — 内部产品主数据（8 个 SKU），含基础计量单位（base_uom）和每箱件数（pack_size）。
- `supplier_mapping.csv` — 供应商编号 → SKU 的**带生效日期的版本化映射**，同一供应商编号可有多个版本（重新包装/退出）。
- `goods_received.csv` — 按供应商编号记录的收货流水，是差异检测的入口。
- `inventory.csv` — 按内部 SKU 记录的每日库存快照，用于数量口径对照。
- `change_requests.csv` — 变更请求队列（未决策），模拟真实工作流中"先申请后审批"的环节。

**English:** Five tables form an evidence chain:

- `products.csv` — internal product master (8 SKUs) with base unit of measure and pack size.
- `supplier_mapping.csv` — **versioned** supplier-code → SKU mapping with effective-date windows; one supplier code may have multiple versions (re-pack/retire).
- `goods_received.csv` — receiving records keyed by supplier code; the entry point for discrepancy detection.
- `inventory.csv` — daily inventory snapshots keyed by internal SKU for quantity comparison.
- `change_requests.csv` — pending (pre-decision) change requests, simulating "request → approve" workflow.

---

## 3. 版本化映射机制 / Versioned Mapping Mechanism

**中文：** 映射表每行都有 `effective_from` / `effective_to`。解析收货记录时，按 `(supplier, supplier_item_code)` 匹配，并要求收货日期落在生效窗口内。设计要点：

- 重新包装（如 10kg→12kg 箱规）= 新增一个版本，旧版本关闭，**不覆盖历史**。
- 生效日当天或 ±2 天内的收货标记为 `near_boundary`（高风险窗口）。
- 若同一 `(supplier, code)` 在同一窗口内匹配到**多于一行** → 判定 `ambiguous_mapping`，进人工队列。
- 若收货日期不在任何版本窗口内 → 区分 `expired_mapping`（历史上有过）与 `missing_mapping`（从未有过），两者都进队列。

**English:** Every mapping row carries `effective_from` / `effective_to`. At resolution time we match on `(supplier, supplier_item_code)` and require the receipt date to fall inside the effective window. Key design points:

- A re-pack (e.g. 10kg → 12kg case) adds a new version and closes the old one; **history is never overwritten**.
- Receipts on the boundary date or within ±2 days are flagged `near_boundary`.
- If more than one mapping version matches the same window → `ambiguous_mapping`, routed to review.
- If no version covers the receipt date → distinguish `expired_mapping` (existed historically) from `missing_mapping` (never existed); both go to the queue.

---

## 4. 差异检测算法 / Detection Algorithms

**中文：** 五类检测，全部在 `pipeline_core.py` 与 `uom_checks.py` 中实现：

1. **重复键 / Duplicate key** — `(supplier, supplier_item_code, batch_ref)` 三元组相同视为重复；保留最早 `receipt_id`，后续标记 `is_duplicate` 并排除出报表切片。
2. **过期映射 / Expired mapping** — 收货日期超出所有版本生效窗口。
3. **缺失映射 / Missing mapping** — 该供应商编号从未存在映射记录。
4. **歧义映射 / Ambiguous mapping** — 同编号同一窗口匹配多个 SKU（NF-AMB-01 同时映射到蓝莓和面粉），**这是"不能自动判定"的典型案例**。
5. **单位与箱规 / UoM & pack size** — 供应商发货单位与内部基础单位不一致时加 `uom_note`；映射箱规与产品主数据不同时加 `pack_size_changed`。

**English:** Five detection classes, implemented in `pipeline_core.py` and `uom_checks.py`:

1. **Duplicate key** — same `(supplier, supplier_item_code, batch_ref)` triple; earliest `receipt_id` kept, later ones flagged and excluded from reporting.
2. **Expired mapping** — receipt date outside every version's window.
3. **Missing mapping** — supplier code has no mapping row at all.
4. **Ambiguous mapping** — same code matches multiple SKUs in one window (NF-AMB-01 → both blueberries and flour); the canonical "cannot auto-resolve" case.
5. **UoM & pack size** — flag supplier vs internal unit mismatch (`uom_note`) and mapping-vs-master pack-size change (`pack_size_changed`).

---

## 5. 审批工作流与审计轨迹 / Approval Workflow & Audit Trail

**中文：** `approval_workflow.py` 模拟人工决策：

- 四条变更请求：CR-001（重新包装批准）、CR-002（退役旧映射批准）、CR-003（歧义编号**拒绝**——证据不足）、CR-004（单位转换批准）。
- 每条决策写入 `decision_log.csv`：决策 ID、审批人、原因、时间戳。
- **幂等设计 / Idempotent design：** `decision_id = SHA1(cr_id + action + decision_ts)`，时间戳是确定性模拟值，重跑不会产生重复日志。
- 批准的变更只作用于工作副本 `mapping_with_approved_changes.csv`，**原始映射表永不被修改**。
- 未批准的记录（如 NF-AMB-01）保持待确认状态，不进入正式报表切片。

**English:** `approval_workflow.py` simulates human decisions:

- Four change requests: CR-001 (re-pack, approved), CR-002 (retire legacy mapping, approved), CR-003 (ambiguous code — **rejected** for insufficient evidence), CR-004 (UoM conversion, approved).
- Every decision is written to `decision_log.csv`: decision ID, approver, reason, timestamp.
- **Idempotent design:** `decision_id = SHA1(cr_id + action + decision_ts)`; timestamps are deterministic simulated values, so re-runs never duplicate log entries.
- Approved changes apply only to the working copy `mapping_with_approved_changes.csv`; **raw mapping is never mutated**.
- Unapproved items (e.g. NF-AMB-01) remain pending and never enter the reporting slice.

---

## 6. 测试用例设计哲学 / Test Case Philosophy

**中文：** `docs/labeled_cases.csv` 含 12 个手工标注案例，覆盖正常、重复、过期、歧义、生效边界、迟到记录等场景。其中 **6 个是正常案例**（TC-01/08/09/10/11/12），目的是防止"把所有差异都当错"的过度触发。`test_labeled_cases.py` 有一条护栏断言：任何 `category=normal` 的记录出现在评审队列中就判失败。

**English:** `docs/labeled_cases.csv` holds 12 hand-labeled cases covering normal, duplicate, expired, ambiguous, boundary, and late-arriving scenarios. Six of them are **normal cases** (TC-01/08/09/10/11/12) to prevent over-flagging. `test_labeled_cases.py` enforces a guard-rail assertion: any `category=normal` record appearing in the review queue fails the suite.

---

## 7. 面试问题到代码的映射 / Interview Questions → Code

**中文：**

1. *"同一 SKU 包装规格变化 vs 两个不同产品编号冲突，处理区别？"*
   → 包装变化走**版本化映射**（新旧版本按生效日切换，CR-001）；编号冲突走**人工队列**（CR-003 拒绝），绝不自动合并。见 `pipeline_core.py: resolve_mappings`。
2. *"谁可以批准更改，为什么不能用模糊匹配或 LLM 直接合并？"*
   → 只有具名审批人（master-data-lead / warehouse-supervisor）能批准；NF-AMB-01 的歧义被拒绝正是因为证据不足。模糊匹配会把蓝莓和面粉混为一谈，后果是库存与成本错误。见 `approval_workflow.py: make_decisions`。
3. *"批准后发现有误，如何找受影响记录、保留审计并重跑报表？"*
   → 受影响记录可按 `mapping_id` / `supplier_item_code` 回溯；`decision_log.csv` 完整保留谁/何时/为何批准；删除决策日志重跑即可回滚，`before_after` 表给出前后对照。见 `generate_reports.py: build_before_after`。

**English:**

1. *"Same-SKU pack change vs. conflicting product codes — what's the difference in handling?"*
   → Pack changes use **versioned mappings** (old/new versions by effective date, CR-001); code conflicts go to the **review queue** (CR-003 rejected), never auto-merged. See `pipeline_core.py: resolve_mappings`.
2. *"Who can approve changes, and why not fuzzy-match or LLM-merge?"*
   → Only named approvers (master-data-lead / warehouse-supervisor) can approve; NF-AMB-01 was rejected precisely due to insufficient evidence. Fuzzy matching would merge blueberries with flour, causing inventory and cost errors. See `approval_workflow.py: make_decisions`.
3. *"If an approval turns out wrong, how do you find affected records, keep the audit, and rerun reports?"*
   → Affected records are traceable via `mapping_id` / `supplier_item_code`; `decision_log.csv` preserves who/when/why; delete the decision log and re-run to roll back; `build_before_after` provides the before/after comparison. See `generate_reports.py`.

---

## 8. 重跑与回滚 / Replay & Rollback

**中文：** 一键重跑（数据 → 核查 → 审批 → 测试 → 报告）：

```bash
python src/generate_synthetic_data.py && python src/run_investigation.py && python src/approval_workflow.py && python src/test_labeled_cases.py && python src/generate_reports.py
```

回滚：删除 `data/processed/decision_log.csv` 后重跑审批工作流；由于决策 ID 确定性，不会产生重复。原始 CSV 始终不变。

**English:** One-command replay (data → investigate → approve → test → report):

```bash
python src/generate_synthetic_data.py && python src/run_investigation.py && python src/approval_workflow.py && python src/test_labeled_cases.py && python src/generate_reports.py
```

Rollback: delete `data/processed/decision_log.csv` and re-run the approval workflow; deterministic decision IDs prevent duplicates. Raw CSVs are never mutated.

---

## 9. 已知边界 / Known Boundaries

**中文：** 本切片故意不做：客户/价格主数据、BOM、成本会计、完整 ERP、真实 Power BI Service 部署、生产权限审批。报表采用 Excel + Markdown（最省事且可审计），不引入新云资源。

**English:** Intentionally out of scope: customer/price master data, BOM, cost accounting, full ERP, real Power BI Service deployment, production authorization. Reporting uses Excel + Markdown (leanest, fully auditable) with no new cloud resources.
