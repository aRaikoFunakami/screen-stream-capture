FROM node:20-alpine as build

WORKDIR /app

# 依存関係をコピーしてインストール
COPY package*.json ./
RUN npm ci

# react-android-screen パッケージをコピー
COPY ../../../packages/react-android-screen /packages/react-android-screen

# ソースをコピーしてビルド
COPY . .
RUN npm run build

# 本番用 nginx
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
