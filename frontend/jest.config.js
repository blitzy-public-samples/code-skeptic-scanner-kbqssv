/**
 * Jest configuration for the frontend suite.
 *
 * Every script in `frontend/package.json` invokes Jest from `frontend/`, so `<rootDir>` is
 * `frontend/`. Coverage is written to `frontend/coverage/` and the JUnit report to
 * `frontend/reports/`.
 *
 * @see frontend/TESTING.md - the dual-transformer arrangement, and every `moduleNameMapper`
 *   substitution together with the importer each one serves.
 * @see docs/testing/DECISION-LOG.md - rows D30-D37 for the transforms, mappers, coverage gate and
 *   reporters, D71 for the coverage denominator, D92 for the shims not installed, and D146 for the
 *   timezone pin.
 */

'use strict';

/*
 * Timezone pin, set in the main process before any worker is spawned: every suite renders local date
 * parts in UTC.
 *
 * @see frontend/src/utils/dateUtils.test.ts - the `formatDate` assertions this pin governs.
 * @see docs/testing/DECISION-LOG.md - row D146.
 */
process.env.TZ = 'UTC';

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

/*
 * Canonical test identity, shared with `src/test-utils/handlers.ts`:
 *
 *   <rootDir-relative test file, forward slashes> > <every enclosing describe title and the leaf title,
 *                                                    joined by a single space>
 *
 * `<testcase classname>` carries the left side and `<testcase name>` the right, so the two joined by ` > `
 * are the string `currentTestId()` returns and stamps on every intercepted-request and contract-violation
 * record. The right side is also Jest's own `currentTestName`, so it is a valid `jest -t` pattern verbatim.
 *
 * `jest-junit` builds its `{filepath}` with `path.relative`, so on Windows it arrives with backslashes;
 * `{title}` is the leaf title alone and `{classname}` the ancestor titles joined by `ancestorSeparator`.
 * The two helpers below are what the reporter options apply to those variables.
 *
 * @see frontend/src/test-utils/handlers.ts - `currentTestId`, the other half of this shape.
 */
const toPosixPath = (value) => String(value).replace(/\\/g, '/');

/**
 * The already-joined ancestor titles (`{classname}`) followed by the leaf title, in the order and with the
 * separator Jest reports them in. A test with no enclosing `describe` is its leaf title alone.
 */
const toFullTestName = (joinedAncestorTitles, title) =>
  joinedAncestorTitles ? `${joinedAncestorTitles} ${title}` : title;

module.exports = {
  /*
   * `ts-jest`'s preset. Its own `transform` entry, `'^.+\\.tsx?$'`, is merged in after the two
   * declared below and is therefore shadowed by them: Jest matches transform patterns in
   * declaration order and takes the first hit.
   */
  preset: 'ts-jest',

  testEnvironment: 'jsdom',

  /* Registers the jest-dom matchers and the msw request-interception lifecycle. */
  setupFilesAfterEnv: ['<rootDir>/src/test-utils/setup-jest.ts'],

  /*
   * Two transformers, matched in declaration order: the extension-less component modules,
   * then every .ts/.tsx/.js/.jsx file. Both are declared here rather than left to the preset,
   * because only these two carry the inline compiler options and `diagnostics: false`.
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
   * Console output, then JUnit XML at `frontend/reports/jest-junit.xml`, with every `<testcase>` carrying
   * the canonical identity defined above: `classname` the `/`-separated test file, `name` the ancestor
   * titles and the leaf title. Two tests that share a leaf title under different `describe` blocks are
   * therefore distinct, and each `<testcase>` matches the ledger entry of the requests it made.
   *
   * The templates are functions rather than `{...}` strings because a string cannot normalise a separator
   * and `{title}` expands to the leaf title alone. `ancestorSeparator` is the single space Jest joins those
   * titles with, and it reaches the emitted name through the `{classname}` variable.
   *
   * `reportTestSuiteErrors` emits a suite that failed to load - jest-junit names such a suite by its raw
   * platform path and cannot be templated there. `addFileAttribute` adds the `file` attribute CI annotators
   * read, also the raw platform path; `includeConsoleOutput` carries the console lines Jest buffers into
   * `<system-out>`.
   */
  reporters: [
    'default',
    [
      'jest-junit',
      {
        outputDirectory: '<rootDir>/reports',
        outputName: 'jest-junit.xml',
        suiteNameTemplate: ({ filepath }) => toPosixPath(filepath),
        classNameTemplate: ({ filepath }) => toPosixPath(filepath),
        titleTemplate: ({ classname, title }) => toFullTestName(classname, title),
        ancestorSeparator: ' ',
        addFileAttribute: 'true',
        reportTestSuiteErrors: 'true',
        includeConsoleOutput: 'true',
      },
    ],
  ],

  /* Clears mock call bookkeeping between tests; implementations are left in place. */
  clearMocks: true,
};
