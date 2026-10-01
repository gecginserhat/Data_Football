import { FlatCompat } from "@eslint/eslintrc";
import tseslint from "typescript-eslint";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default tseslint.config(
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "next-env.d.ts",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          // Yasak adlar: ANTHROPIC_API_KEY ve ANTHROPIC_MODEL (CLAUDE.md). KURGU_ önekli adlar serbesttir.
          selector: "Literal[value=/(^|[^_])\\bANTHROPIC_(API_KEY|MODEL)/]",
          message: "Use KURGU_ANTHROPIC_API_KEY / KURGU_LLM_MODEL (CLAUDE.md).",
        },
      ],
    },
  },
);
