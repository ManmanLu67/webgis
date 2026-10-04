import js from "@eslint/js"
import pluginVue from "eslint-plugin-vue"
import tseslint from "typescript-eslint"
import vueParser from "vue-eslint-parser"

/**
 * 规则按文件类型分档，分工是有意的：
 *
 * - **模板结构与命名**归 ESLint。`vue/multi-word-component-names`、
 *   `vue/no-undef-properties` 这类规则 ESLint 比 vue-tsc 强，而且零成本。
 * - **props / emit / 模板表达式的类型**归 vue-tsc（`pnpm build` 的前置步骤）。
 *
 * `.vue` 上刻意不启用类型感知规则：那些规则需要 TypeScript 语言服务，会把 lint
 * 从秒级拖到数十秒，而且报出来的问题与 `vue-tsc --noEmit` 高度重复。两边都开等于
 * 同一批错误报两遍，维护者只会习惯性地忽略其中一个。所以下面**没有**配
 * `parserOptions.project` / `projectService`。
 *
 * ## 解析器 ≠ 类型感知
 *
 * `.vue` 那段仍然要用 `typescript-eslint` 的**解析器**，但那只是语法层面的：
 * 没有它，espree 认不出 `import { type Foo } from "./x"` 这种写法，会直接报
 * Parsing error。解析器只负责把源码变成 AST，不需要类型信息。
 *
 * 换成一句话：我们要 TS **语法**，不要 TS **类型检查**。后者归 vue-tsc。
 *
 * 关于 emit 的类型标注：eslint-plugin-vue **没有** `require-typed-prop-emits` 这条
 * 规则（写过这个计划的人记错了）。它靠不靠得住其实已经有答案——阶段 A 把模板里的
 * `emit('sketch','point')` 改成 `'poitn'`，是 `vue-tsc` 报的 TS2769。那就归
 * vue-tsc 管，这里不重复。
 */
/* 关掉的规则，以及为什么
 *
 * no-undef
 *   TypeScript 自己就会报未定义的标识符，而且信息更全（能区分类型层与值层）。
 *   ESLint 官方给 TS 的指引就是关掉它：它认不全 TS 的语法，还会和 vue-tsc
 *   重复报同一件事。这里原本会报 16 条 URL / Blob / File / crypto 之类的假错。
 *
 * vue/max-attributes-per-line、vue/singleline-html-element-content-newline、
 * vue/html-self-closing、vue/attributes-order
 *   纯格式规则，合计 284 条。本项目刻意不引 prettier（会产生大量与改动无关的
 *   diff），要格式化也不该由 ESLint 代理。它们的唯一作用是让每个 diff 都难读。
 *
 * vue/require-default-prop
 *   在 `<script setup>` + `defineProps<T>()` 下没有意义：可选性写在类型里
 *   （`foo?: string`），再要求写 default 是重复表达。
 */
const TURNED_OFF = {
  // TypeScript 已经做得更好
  "no-undef": "off",
  // 格式类，交给人的判断
  "vue/max-attributes-per-line": "off",
  "vue/singleline-html-element-content-newline": "off",
  "vue/html-self-closing": "off",
  "vue/attributes-order": "off",
  "vue/html-indent": "off",
  "vue/html-closing-bracket-newline": "off",
  // defineProps<T>() 下无意义
  "vue/require-default-prop": "off",
  "vue/require-prop-types": "off",
}

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "*.config.js", "*.config.ts"],
  },

  /* ---------- .ts ---------- */
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.ts"],
    languageOptions: {
      globals: { console: "readonly", window: "readonly", document: "readonly" },
    },
    rules: {
      // 接口返回的 JSON 默认是 any。契约已在 api/layerSpec.ts 里收窄过一遍，
      // 这里禁止再随手写 any —— 要么写 unknown 让下游收窄，要么写具体类型。
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // 空 catch 会把错误吃掉。之前 loadSources / loadAnnotations 就是这么写的，
      // 出错时界面上什么都不会显示。
      "no-empty": ["error", { allowEmptyCatch: false }],
      eqeqeq: ["error", "smart"],
      ...TURNED_OFF,
    },
  },

  /* ---------- .vue：只开非类型感知规则 ---------- */
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["src/**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        // 只给解析器，不给 project —— 给了 project 就变成类型感知了
        parser: tseslint.parser,
        ecmaVersion: "latest",
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
      globals: { console: "readonly", window: "readonly", document: "readonly" },
    },
    rules: {
      // 模板里引用了不存在的属性 —— 这类错 vue-tsc 抓不到（模板里的表达式
      // 在类型层面常常退化成 any），但用户在界面上会直接看到空白。
      "vue/no-undef-properties": "error",
      "vue/multi-word-component-names": "error",
      "vue/no-mutating-props": "error",
      "vue/no-async-in-computed-properties": "error",
      "vue/no-side-effects-in-computed-properties": "error",
      "vue/no-v-html": "error",
      eqeqeq: ["error", "smart"],
      ...TURNED_OFF,
    },
  },

  /* ---------- 测试文件：允许更松 ---------- */
  {
    files: ["src/**/*.test.ts"],
    rules: {
      // 测试里构造不完整的对象是常态，比如故意少给一个字段
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
)
