-- 企业知识库系统 - MySQL 初始化
-- 版本: V3.0
--
-- 说明：本脚本仅负责创建数据库（以及由 MySQL 镜像环境变量创建的应用账号）。
-- 业务表统一由后端 `python -m app.scripts.init_schema` 经 Base.metadata.create_all()
-- 全量幂等创建（按当前 ORM 模型的最终 schema），基础种子数据（分类/超管/敏感词/权限）
-- 亦由该脚本幂等写入。避免 init SQL 与 ORM/迁移双轨维护造成的 schema 漂移。

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS knowledge_base
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE knowledge_base;
