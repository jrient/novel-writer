# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app

# 复制依赖文件并安装
COPY package.json package-lock.json* ./
RUN npm install

# 复制源码并构建
COPY . .
RUN npm run build

# 生产阶段：使用 nginx 提供静态文件
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
