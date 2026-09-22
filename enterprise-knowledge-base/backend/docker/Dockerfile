# Backend Dockerfile - 多阶段构建
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ARG APP_VERSION=dev
LABEL version=$APP_VERSION

WORKDIR /app

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Node.js (Wechatsync CLI 依赖)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @wechatsync/cli && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# ========== Dev Stage ==========
FROM base AS dev
RUN pip install --no-cache-dir -r requirements.txt \
      -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip install --no-cache-dir email-validator dnspython -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
# OCR 运行时（独立追加层：不触碰上面的主依赖缓存层，避免重装 torch）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "rapidocr-onnxruntime>=1.3.20,<1.4.0" \
      -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
EXPOSE 8000

# ========== Production Stage ==========
FROM base AS prod
RUN pip install --no-cache-dir -r requirements.txt \
      -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip install --no-cache-dir email-validator dnspython -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "rapidocr-onnxruntime>=1.3.20,<1.4.0" \
      -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
COPY . .
RUN mkdir -p /app/models
RUN addgroup --gid 1001 --system app && adduser --system app --uid 1001 --ingroup app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
