/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    // react-android-screen パッケージ内のコンポーネント
    // ローカル開発: ../../../packages/react-android-screen
    // Docker 環境: /app/packages/react-android-screen
    "../../../packages/react-android-screen/src/**/*.{js,ts,jsx,tsx}",
    "/app/packages/react-android-screen/src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
