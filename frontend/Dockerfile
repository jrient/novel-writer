# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app

# 先只复制依赖文件，利用 Docker 缓存层
COPY package.json package-lock.json ./

# 设置 npm 镜像加速并安装依赖
RUN npm config set registry https://registry.npmmirror.com && \
    npm ci --prefer-offline --no-audit

# 复制源码并构建（跳过类型检查）
COPY . .
RUN npm run build:docker

# 生产阶段：使用 nginx 提供静态文件
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
