# 数据驱动优化流程

> 阶段 D2 — 基于真实反馈的持续优化迭代

## 优化流程总览

```
收集阶段 (持续)
  ├── 未命中 Top 20（unanswered_question 表统计）
  ├── 用户评价分布（feedback 表 rating 字段）
  ├── 性能瓶颈（chat_log 表 node_latency_ms）
  └── 安全事件（security_log 表 event_type）

分析阶段 (每周)
  ├── 知识缺口分析 → 哪些问题用户问得多但没答案
  ├── 质量分析 → 哪些 FAQ 差评多需要改进
  ├── 延迟分析 → 哪个 LangGraph 节点最慢
  └── 安全分析 → 哪些攻击模式需要加强防护

优化阶段 (按优先级)
  ├── 补充缺失知识（Top 20 未命中 → 写 FAQ 或长文档 → 审核上线）
  ├── 修正低质内容（差评 FAQ → 改写答案 → 重新上线）
  ├── 调整检索参数（召回阈值、RRF k 值、Reranker Top-K）
  ├── 优化 Prompt 模板（bad case 分析 → 调整 system prompt）
  ├── 调整分块策略（特定文档类型的分块参数优化）
  └── 延迟瓶颈优化（chat_log.node_latency_ms → 定位最慢节点）
```

## 数据查询

### 未命中 Top 20

```sql
SELECT question, COUNT(*) as cnt
FROM unanswered_question
WHERE status = 'pending'
GROUP BY question
ORDER BY cnt DESC
LIMIT 20;
```

### 差评 FAQ Top 10

```sql
SELECT f.question, COUNT(*) as dislike_cnt
FROM feedback fb
JOIN chat_log cl ON fb.thread_id = cl.thread_id
JOIN knowledge_faq f ON cl.hit_faq_id = f.id
WHERE fb.rating = 'dislike'
GROUP BY f.question
ORDER BY dislike_cnt DESC
LIMIT 10;
```

### 节点延迟分析

```sql
SELECT node_name, AVG(node_latency_ms) as avg_ms,
       MAX(node_latency_ms) as max_ms,
       COUNT(*) as calls
FROM chat_log
WHERE node_latency_ms > 0
GROUP BY node_name
ORDER BY avg_ms DESC;
```

### 用户满意度趋势（按月）

```sql
SELECT DATE_FORMAT(created_at, '%Y-%m') as month,
       COUNT(*) as total,
       SUM(CASE WHEN rating='like' THEN 1 ELSE 0 END) as likes,
       SUM(CASE WHEN rating='dislike' THEN 1 ELSE 0 END) as dislikes
FROM feedback
GROUP BY month
ORDER BY month;
```

## 检索参数调优

| 参数 | 默认值 | 调优建议 | 文件 |
|------|--------|---------|------|
| FAQ 余弦阈值 | 0.92 | 差评多→降低；未命中多→降低 | `agents/nodes/faq.py` |
| RRF k 值 | 60 | 大文档集→提高 | `retrieval/fusion.py` |
| Reranker Top-K | 5 | 低置信→提高 | `agents/nodes/retrieve.py` |
| 分块大小 | 800 | 长文档→增大 | `services/chunking.py` |
| 分块重叠 | 200 | 检索断句→增大 | `services/chunking.py` |

## Prompt 优化

| 智能体 | Prompt 文件 | 优化要点 |
|--------|------------|---------|
| 内部问答 | `agents/nodes/generate.py` | 引用来源准确性 |
| 客服咨询 | `agents/customer/generate.py` | 语气亲和力、转人工时机 |

## 迭代记录模板

每次优化后填写：

```
---
迭代编号: OPT-001
日期: YYYY-MM-DD
触发: 未命中 Top 1 "XXX" 本月查询 47 次

变更:
  - 新增 FAQ: "XXX" → "XXX"
  - 调整参数: Reranker Top-K 5 → 8

效果:
  - 未命中次数: 47/月 → 0/月
  - 用户满意度: 82% → 91%

验证人: XXX
---
```
