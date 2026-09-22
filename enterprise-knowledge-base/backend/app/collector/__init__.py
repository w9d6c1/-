"""多源官方内容采集层 — 独立于问答服务的内容接入模块。

架构：采集器（adapters）→ 清洗（cleaner）→ 去重（dedup）→ 入库（ingestion），
由 pipeline 编排，单平台故障隔离。所有外部内容强制 scope=public。
"""
