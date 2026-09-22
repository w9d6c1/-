"""企业知识库系统 - 配置管理"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "企业知识库系统"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "DEBUG"

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "kb_user"
    mysql_password: str = "kb_pass_2024"
    mysql_database: str = "knowledge_base"

    # PostgreSQL (LangGraph Checkpoint)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "pg_pass_2024"
    postgres_db: str = "langgraph_checkpoint"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # Elasticsearch
    es_host: str = "localhost"
    es_port: int = 9200

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "knowledge-docs"
    max_upload_size_mb: int = 50

    # LLM
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"

    # LLM Backup (主模型不可用时切换)
    llm_backup_provider: str = ""
    llm_backup_api_key: str = ""
    llm_backup_model: str = ""
    llm_backup_base_url: str = ""

    # Embedding
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_device: str = "cpu"
    # FAQ 专用轻量 embedding 模型（路线 A 解耦）。
    # 留空则回退到 embedding_model，保证小模型未下载时 FAQ 仍可用。
    faq_embedding_model: str = ""

    # Reranker
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"

    # SiliconFlow API (embedding + reranker 云端替代本地模型)
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # 阿里云 SMS (手机验证码)
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""
    sms_sign_name: str = ""
    sms_template_code: str = ""

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Webhook 通知 (企微/钉钉)
    webhook_url: str = ""

    # 企业微信 (内部智能体渠道)
    wecom_corp_id: str = ""
    wecom_agent_id: int = 0
    wecom_secret: str = ""
    wecom_token: str = ""
    wecom_aes_key: str = ""
    # 企微渠道默认角色 (决定 scope 权限)
    wecom_default_role: str = "operator"

    # 企微问答兜底 — 检索不到相关内容时的固定拒绝语（可用 NO_ANSWER_REPLY 覆盖）
    no_answer_reply: str = "抱歉，知识库中暂未收录该问题的相关信息，无法准确回答。建议您换个问法，或联系管理员补充相关资料。"

    # FAQ 命中时直接返回维护好的答案，跳过 LLM 重新加工（大幅提速）
    faq_direct_answer: bool = True
    # 企微渠道收到消息后先推送一条确认语，再异步生成最终答案（避免用户以为没反应）
    wecom_send_ack: bool = True
    wecom_ack_reply: str = "已收到，正在查询知识库，请稍候…"

    # 腾讯云语音识别 (企微语音消息转文字，一句话识别 SentenceRecognition)
    tencent_secret_id: str = ""
    tencent_secret_key: str = ""
    asr_engine_type: str = "16k_zh"

    # 日志留存
    chat_log_retention_days: int = 180

    # 视觉模型（图片分析）— OpenAI 兼容接口
    vision_model_provider: str = "openai_compatible"
    vision_model_api_key: str = ""
    vision_model_name: str = "Qwen/Qwen2-VL-72B-Instruct"
    vision_model_base_url: str = "https://api.siliconflow.cn/v1"

    # LLM 全局采样参数
    llm_top_p: float = 0.9
    # 多轮历史送入 LLM 的 token 上限（超出保留最近部分）
    history_max_tokens: int = 8000

    # 文章生成
    article_default_count: int = 5
    article_min_words: int = 1200
    article_max_words: int = 3000
    article_temperature: float = 0.6
    article_top_p: float = 0.85
    article_generate_interval: float = 3.0

    # 发布
    wechatsync_cli_path: str = "wechatsync"
    publisher_bridge_url: str = "http://host.docker.internal:3010"
    wechat_mp_appid: str = ""
    wechat_mp_appsecret: str = ""
    # 发布配图的公开访问基址（扩展/微信直连拉取照片；自签名证书建议配 http 内网地址）
    publish_public_base_url: str = "https://localhost"

    # 多源采集平台凭证 / 配置（阶段二）
    wechat_mp_source_name: str = "公司官方公众号"
    toutiao_access_token: str = ""
    toutiao_source_name: str = "公司官方头条号"
    zhihu_access_secret: str = ""
    zhihu_cookie: str = ""
    zhihu_fetch_fulltext: bool = True
    zhihu_page_delay: float = 1.0
    zhihu_source_name: str = "公司官方知乎号"
    bilibili_access_token: str = ""
    bilibili_mid: str = ""
    bilibili_source_name: str = "公司官方B站专栏"
    official_website_base_url: str = ""
    official_website_list_path: str = ""
    official_website_source_name: str = "企业官网"
    collector_default_category_id: int = 1
    collector_request_timeout: float = 20.0
    collector_sync_hour: int = 2
    collector_sync_minute: int = 0
    collector_max_pages_per_sync: int = 50

    # OCR（扫描版 PDF 兜底识别；pdf_ocr_enabled=1 时低文字量页自动走 RapidOCR）
    pdf_ocr_enabled: bool = False
    ocr_min_chars_per_page: int = 30
    ocr_dpi: int = 200
    ocr_model_dir: str = "/app/ocr_models"
    ocr_batch_pages: int = 200

    # 照片库
    photo_reuse_window_days: int = 30
    photo_match_count: int = 5
    # 权重匹配系数（LLM 语义分 + 规则加权，和应为 1.0）
    photo_match_weights: dict = {
        "tag_keyword": 0.4,
        "semantic": 0.3,
        "freshness": 0.2,
        "anti_reuse": 0.1,
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mysql_url(self) -> str:
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        pw = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pw}{self.redis_host}:{self.redis_port}/0"

    @property
    def es_url(self) -> str:
        return f"http://{self.es_host}:{self.es_port}"


settings = Settings()
