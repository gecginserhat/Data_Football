// Paylaşılan paketler (packages/*) için ESLint. apps/web kendi yapılandırmasını kullanır.
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["**/dist/**", "**/node_modules/**", "**/*.d.ts", "apps/**"] },
  ...tseslint.configs.recommended,
  {
    files: ["packages/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: { ...reactHooks.configs.recommended.rules },
  },
);
