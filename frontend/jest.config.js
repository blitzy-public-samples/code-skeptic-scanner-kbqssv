/**
 * Jest configuration for the frontend suite.
 *
 * Every script in `frontend/package.json` invokes Jest from `frontend/`, so `<rootDir>` is
 * `frontend/`. Coverage is written to `frontend/coverage/` and the JUnit report to
 * `frontend/reports/`.
 *
 * @see frontend/TESTING.md - the dual-transformer arrangement, and every `moduleNameMapper`
 *   substitution together with the importer each one serves.
 * @see docs/testing/DECISION-LOG.md - section 3, the single source of truth for why each setting
 *   below is what it is, including the options and shims deliberately not used.
 */

'use strict';

/*
 * Inline ts-jest compiler options - no tsconfig file is read. Mirrored in
 * `frontend/jest.transform.extensionless.js`, which adds `isolatedModules`.
 */
const TSCONFIG = {
  jsx: 'react-jsx',
  module: 'commonjs',
  esModuleInterop: true,
  allowJs: true,
  target: 'ES2020',
};

module.exports = {
  testEnvironment: 'jsdom',

  /* Registers the jest-dom matchers and the msw request-interception lifecycle. */
  setupFilesAfterEnv: ['<rootDir>/src/test-utils/setup-jest.ts'],

  /*
   * Two transformers, matched in declaration order: the extension-less component modules,
   * then every .ts/.tsx/.js/.jsx file. No `preset` is declared.
   */
  transform: {
    'src[\\\\/]components[\\\\/](Dashboard|TweetManagement|Analytics|Configuration)$':
      '<rootDir>/jest.transform.extensionless.js',
    '^.+\\.[jt]sx?$': ['ts-jest', { tsconfig: TSCONFIG, diagnostics: false }],
  },

  /* Module resolution order; the trailing empty string covers the extension-less modules. */
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node', ''],

  /*
   * Four groups, evaluated in declaration order: the four extension-less component modules; three
   * specifiers with no implementation, sent to test-side stubs, `configSchema` matched in both the
   * relative form `store/configSlice.ts` uses and an aliased form; three bare specifiers that do
   * not resolve; then the generic `@/*` alias mirroring `tsconfig.json`.
   */
  moduleNameMapper: {
    '^@/components/Dashboard$': '<rootDir>/src/components/Dashboard',
    '^@/components/TweetManagement$': '<rootDir>/src/components/TweetManagement',
    '^@/components/Analytics$': '<rootDir>/src/components/Analytics',
    '^@/components/Configuration$': '<rootDir>/src/components/Configuration',

    '^@/services/analyticsService$': '<rootDir>/src/test-utils/stubs/analyticsService.ts',
    '^@/services/configService$': '<rootDir>/src/test-utils/stubs/configService.ts',
    '^\\.\\./schema/configSchema$': '<rootDir>/src/test-utils/stubs/configSchema.ts',
    '^@/schema/configSchema$': '<rootDir>/src/test-utils/stubs/configSchema.ts',

    '^app/schema/tweet$': '<rootDir>/src/schema/tweetSchema.ts',
    '^app/schema/user$': '<rootDir>/src/schema/userSchema.ts',
    '^app/services/api$': '<rootDir>/src/services/api.ts',

    '^@/(.*)$': '<rootDir>/src/$1',
  },

  /* Coverage denominator: the glob, the four extension-less paths, then the exclusions. */
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    'src/components/Dashboard',
    'src/components/TweetManagement',
    'src/components/Analytics',
    'src/components/Configuration',
    '!src/app.tsx',
    '!src/**/*.test.{ts,tsx}',
    '!src/test-utils/**',
    '!src/**/*.d.ts',
  ],

  /* Runner-enforced gate, scoped to three packages; no global group. */
  coverageThreshold: {
    './src/store': { statements: 80, branches: 80, functions: 80, lines: 80 },
    './src/schema': { statements: 80, branches: 80, functions: 80, lines: 80 },
    './src/services': { statements: 80, branches: 80, functions: 80, lines: 80 },
  },

  /* Coverage output formats. `json` emits coverage/coverage-final.json. */
  coverageReporters: ['text-summary', 'lcov', 'json', 'json-summary', 'cobertura'],

  /*
   * Console output, then JUnit XML at `frontend/reports/jest-junit.xml`. `<testcase classname>` is
   * the test file and `<testcase name>` the full test name - the same pair
   * `src/test-utils/handlers.ts` stamps, separators normalised to `/`, on every intercepted-request
   * and contract-violation record. `reportTestSuiteErrors` emits a suite that failed to load,
   * `addFileAttribute` the `file` attribute CI annotators read, `includeConsoleOutput` the console
   * lines Jest buffers, under `<system-out>`.
   */
  reporters: [
    'default',
    [
      'jest-junit',
      {
        outputDirectory: '<rootDir>/reports',
        outputName: 'jest-junit.xml',
        suiteNameTemplate: '{filepath}',
        classNameTemplate: '{filepath}',
        titleTemplate: '{title}',
        ancestorSeparator: ' > ',
        addFileAttribute: 'true',
        reportTestSuiteErrors: 'true',
        includeConsoleOutput: 'true',
      },
    ],
  ],

  /* Clears mock call bookkeeping between tests; implementations are left in place. */
  clearMocks: true,
};
