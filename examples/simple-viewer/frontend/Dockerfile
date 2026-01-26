FROM node:20-slim

WORKDIR /app

# NPM パッケージをビルド
COPY packages/react-android-screen /app/packages/react-android-screen
WORKDIR /app/packages/react-android-screen
RUN npm install && npm run build

# フロントエンドをコピー
COPY examples/simple-viewer/frontend /app/frontend
WORKDIR /app/frontend

# Docker 内でのパスに合わせて package.json を修正してからインストール
RUN sed -i 's|file:../../../packages/react-android-screen|file:/app/packages/react-android-screen|g' package.json && npm install

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
