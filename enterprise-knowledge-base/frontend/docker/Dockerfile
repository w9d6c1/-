# Frontend Dockerfile — Vue + React 管理后台合并构建
FROM node:22-alpine AS base
WORKDIR /project

ARG APP_VERSION=dev
LABEL version=$APP_VERSION

# ========== React 管理后台构建 ==========
FROM base AS react-build
WORKDIR /project/app
COPY app/package.json app/package-lock.json ./
RUN npm install --no-audit --no-fund
COPY app/ .
RUN npm run build

# ========== Dev Stage ==========
FROM base AS dev
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend/ .
EXPOSE 5173

# ========== Production Stage ==========
FROM base AS prod
WORKDIR /project/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build
# 合并 React 管理后台构建产物到 dist/app/ 子目录（必须在 vite build 之后，否则被清空）
COPY --from=react-build /project/app/dist ./dist/app

FROM nginx:1.27-alpine AS production
COPY --from=prod /project/frontend/dist /usr/share/nginx/html
COPY frontend/docker/nginx-frontend.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
