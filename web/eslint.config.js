import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Tailwind's default palette is removed (only kit colours exist), so a stray default colour
// class silently renders nothing. Flag them.
const offPalette =
  /\b(?:bg|text|border|ring|fill|stroke|from|to|via)-(?:gray|zinc|neutral|slate|stone|blue|sky|cyan|teal|emerald|lime|amber|purple|violet|fuchsia|rose)-\d/;

export default tseslint.config(
  { ignores: ["dist", "node_modules", "test-results", "playwright-report"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2023, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-hooks/set-state-in-effect": "off",
      "react-refresh/only-export-components": "off",
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=${offPalette}]`,
          message: "Use a kit colour; Tailwind's default palette is disabled.",
        },
      ],
    },
  },
);
