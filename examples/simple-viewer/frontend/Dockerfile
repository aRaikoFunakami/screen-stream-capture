FROM node:20-slim

WORKDIR /app

# NPM パッケージをインストール
COPY packages/react-android-screen /app/packages/react-android-screen
WORKDIR /app/packages/react-android-screen
RUN npm install && npm run build

# フロントエンドに移動
COPY examples/simple-viewer/frontend /app/frontend
WORKDIR /app/frontend
RUN npm install

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
