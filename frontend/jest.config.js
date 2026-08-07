/**
 * Jest configuration for the frontend suite.
 *
 * Every script in `frontend/package.json` invokes Jest from `frontend/`, so `<rootDir>` is
 * `frontend/`. Coverage is written to `frontend/coverage/` and the JUnit report to
 * `frontend/reports/`.
 *
 * @see frontend/TESTING.md - the dual-transformer arrangement, and every `moduleNameMapper`
 *   substitution together with the importer each one serves.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why each setting below is
 *   what it is, including the options and shims deliberately not used.
 */

'use strict';

/* Inline ts-jest compiler options; mirrored in `frontend/jest.transform.extensionless.js`. */
const TSCONFIG = {
  jsx: 'react-jsx',
  module: 'commonjs',
  esModuleInterop: true,
  allowJs: true,
  target: 'ES2020',
};

module.exports = {
  preset: 'ts-jest',

  testEnvironment: 'jsdom',

  /* Registers the jest-dom matchers and the msw request-interception lifecycle. */
  setupFilesAfterEnv: ['<rootDir>/src/test-utils/setup-jest.ts'],

  /* Two transformers: the extension-less component modules, then every .ts/.tsx/.js/.jsx file. */
  transform: {
    'src[\\\\/]components[\\\\/](Dashboard|TweetManagement|Analytics|Configuration)$':
      '<rootDir>/jest.transform.extensionless.js',
    '^.+\\.[jt]sx?$': ['ts-jest', { tsconfig: TSCONFIG, diagnostics: false }],
  },

  /* Module resolution order; the trailing empty string covers the extension-less modules. */
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node', ''],

  /*
   * Four groups, evaluated in declaration order.
   *
   * Group 1 - the four extension-less component modules.
   * Group 2 - three specifiers with no implementation, sent to test-side stubs. `configSchema` is
   *   matched in both the relative form `store/configSlice.ts` uses and an aliased form.
   * Group 3 - three bare specifiers that do not resolve.
   * Group 4 - the generic `@/*` alias mirroring `tsconfig.json`.
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

  /* Console output, then JUnit XML keyed by file path. */
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
      },
    ],
  ],

  /* Clears mock call bookkeeping between tests; implementations are left in place. */
  clearMocks: true,
};
