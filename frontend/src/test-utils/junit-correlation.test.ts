/**
 * Contract of the canonical test identity - the one string that names an executed test in the report a run
 * writes and in the ledger `./handlers` stamps on every request that test made.
 *
 * The identity has two halves, `<rootDir>`-relative test file and full test name, joined by
 * `TEST_ID_SEPARATOR`:
 *
 *     src/services/api.test.ts > fetchTweets propagates the rejection instance unchanged
 *
 * `frontend/jest.config.js` emits the left half as `<testcase classname>` and the right half as
 * `<testcase name>`; `currentTestId()` returns the two already joined. Both halves are load-bearing. Without
 * the file half normalised, the report names a file with backslashes on Windows and the ledger with forward
 * slashes, so the two cannot be matched by equality. Without the ancestor titles in the name half, the four
 * leaf titles `services/twitterService.test.ts` repeats across `getLatestTweets` and `getTweetDetails`, and
 * the three `services/api.test.ts` repeats across its three operations, collapse onto one `<testcase>`
 * identity apiece and a failing result no longer says which operation failed.
 *
 * Neither half is visible in a passing run: every suite stays green while the report is unusable, which is
 * why the contract is asserted here rather than read off an artifact by hand. The cases below apply the
 * reporter's own template functions - read out of `jest.config.js`, not restated - to the variables
 * `jest-junit` builds, and compare the result with what the ledger recorded for the same test.
 *
 * @see frontend/jest.config.js - the templates and the identity they emit.
 * @see frontend/src/test-utils/handlers.ts - `currentTestId`, and the ledger entry that carries it.
 * @see docs/testing/DECISION-LOG.md - section 15.
 */

import * as fs from 'fs';
import * as path from 'path';

import { fetchTweets } from '../services/api';

import { currentTestId, lastRecordedRequest, TEST_ID_SEPARATOR } from './handlers';

/* eslint-disable-next-line @typescript-eslint/no-var-requires */
const jestConfig = require('../../jest.config.js') as { reporters: unknown[] };

/** The variables `jest-junit` hands a template, in the shape `buildJsonResults` assembles them. */
interface TemplateVariables {
  filepath: string;
  filename: string;
  suitename: string | undefined;
  /** Ancestor titles joined by `ancestorSeparator`; the empty string for a test with no `describe`. */
  classname: string;
  /** Leaf title alone. */
  title: string;
  displayName: string | undefined;
}

type Template = (variables: TemplateVariables) => string;

/** The `jest-junit` reporter options as `frontend/jest.config.js` declares them. */
interface JUnitReporterOptions {
  outputDirectory: string;
  outputName: string;
  suiteNameTemplate: Template;
  classNameTemplate: Template;
  titleTemplate: Template;
  ancestorSeparator: string;
  filePathPrefix?: string;
}

/**
 * The options object the config passes to `jest-junit`.
 *
 * @throws If the config declares no `jest-junit` reporter, which would remove the report entirely.
 */
function junitOptions(): JUnitReporterOptions {
  const entry = jestConfig.reporters.find(
    (reporter): reporter is [string, JUnitReporterOptions] =>
      Array.isArray(reporter) && reporter[0] === 'jest-junit',
  );

  if (entry === undefined) {
    throw new Error('frontend/jest.config.js declares no jest-junit reporter');
  }

  return entry[1];
}

const OPTIONS = junitOptions();

/** State of the test currently executing, as this module needs it. */
function jestState(): { currentTestName: string; testPath: string } {
  const state = expect.getState();

  return { currentTestName: state.currentTestName ?? '', testPath: state.testPath ?? '' };
}

/**
 * `jest-junit`'s `{filepath}` for a test file: the path relative to the directory Jest was invoked from,
 * with the platform's own separator, exactly as `buildJsonResults` computes it.
 */
function reporterFilepath(testPath: string): string {
  return path.join(OPTIONS.filePathPrefix ?? '', path.relative(fs.realpathSync(process.cwd()), testPath));
}

/** The variables `jest-junit` would hand its templates for one test case. */
function templateVariables(ancestorTitles: readonly string[], title: string, testPath: string): TemplateVariables {
  const filepath = reporterFilepath(testPath);

  return {
    filepath,
    filename: path.basename(filepath),
    suitename: ancestorTitles[0],
    classname: ancestorTitles.join(OPTIONS.ancestorSeparator),
    title,
    displayName: undefined,
  };
}

/**
 * The identity the report emits for one test case: `<testcase classname>`, the separator, and
 * `<testcase name>`.
 */
function emittedIdentity(ancestorTitles: readonly string[], title: string, testPath: string): string {
  const variables = templateVariables(ancestorTitles, title, testPath);

  return `${OPTIONS.classNameTemplate(variables)}${TEST_ID_SEPARATOR}${OPTIONS.titleTemplate(variables)}`;
}

/* Titles declared once and used both to nest the test and to rebuild what the reporter emits for it. */
const IDENTITY_SUITE = 'the report and the ledger name a test the same way';
const NESTED_SUITE = 'for a test inside nested describe blocks';
const NESTED_LEAF = 'the emitted identity is the id the ledger stamps';
const TOP_LEVEL_LEAF = 'the emitted identity is the ledger id for a test with no enclosing describe';
const REPEATED_LEAF = 'is identified by its describe block, not by this title alone';
const FIRST_OPERATION = 'a first operation';
const SECOND_OPERATION = 'a second operation';

describe('the jest-junit templates', () => {
  it('declares each template as a function, the only form that can normalise a separator', () => {
    expect(typeof OPTIONS.suiteNameTemplate).toBe('function');
    expect(typeof OPTIONS.classNameTemplate).toBe('function');
    expect(typeof OPTIONS.titleTemplate).toBe('function');
  });

  it('rewrites a Windows filepath to forward slashes in the classname and the suite name', () => {
    const variables = templateVariables([], 'a title', jestState().testPath);
    const windowsPath = { ...variables, filepath: 'src\\services\\api.test.ts' };

    expect(OPTIONS.classNameTemplate(windowsPath)).toBe('src/services/api.test.ts');
    expect(OPTIONS.suiteNameTemplate(windowsPath)).toBe('src/services/api.test.ts');
    expect(OPTIONS.classNameTemplate(windowsPath)).not.toContain('\\');
  });

  it('leaves a POSIX filepath untouched', () => {
    const variables = templateVariables([], 'a title', jestState().testPath);
    const posixPath = { ...variables, filepath: 'src/services/api.test.ts' };

    expect(OPTIONS.classNameTemplate(posixPath)).toBe('src/services/api.test.ts');
  });

  it('joins ancestor titles with the single space Jest joins them with', () => {
    expect(OPTIONS.ancestorSeparator).toBe(' ');
  });

  it('puts the ancestor titles ahead of the leaf title in the emitted name', () => {
    const variables = templateVariables(['outer', 'inner'], 'leaf', jestState().testPath);

    expect(variables.classname).toBe('outer inner');
    expect(OPTIONS.titleTemplate(variables)).toBe('outer inner leaf');
  });

  it('names a test with no enclosing describe by its leaf title alone', () => {
    const variables = templateVariables([], 'leaf', jestState().testPath);

    expect(variables.classname).toBe('');
    expect(OPTIONS.titleTemplate(variables)).toBe('leaf');
  });

  it('writes the report to frontend/reports/jest-junit.xml', () => {
    expect(OPTIONS.outputDirectory).toBe('<rootDir>/reports');
    expect(OPTIONS.outputName).toBe('jest-junit.xml');
  });
});

describe(IDENTITY_SUITE, () => {
  describe(NESTED_SUITE, () => {
    it(NESTED_LEAF, () => {
      const { currentTestName, testPath } = jestState();
      const ancestors = [IDENTITY_SUITE, NESTED_SUITE];
      const variables = templateVariables(ancestors, NESTED_LEAF, testPath);

      // The emitted name is Jest's own full test name. `jest -t` takes a regular expression, so
      // selecting a test by that name requires escaping its regex metacharacters first.
      expect(OPTIONS.titleTemplate(variables)).toBe(currentTestName);
      expect(emittedIdentity(ancestors, NESTED_LEAF, testPath)).toBe(currentTestId());
      expect(currentTestId()).toBe(
        `src/test-utils/junit-correlation.test.ts${TEST_ID_SEPARATOR}${currentTestName}`,
      );
    });

    it('stamps that identity on every request the test made', async () => {
      await fetchTweets(3, 25);

      const recorded = lastRecordedRequest();

      expect(recorded).toBeDefined();
      expect(recorded?.violations).toEqual([]);
      expect(recorded?.testId).toBe(currentTestId());
      expect(recorded?.testId).toBe(
        emittedIdentity(
          [IDENTITY_SUITE, NESTED_SUITE],
          'stamps that identity on every request the test made',
          jestState().testPath,
        ),
      );
    });
  });
});

it(TOP_LEVEL_LEAF, () => {
  const { currentTestName, testPath } = jestState();

  expect(currentTestName).toBe(TOP_LEVEL_LEAF);
  expect(emittedIdentity([], TOP_LEVEL_LEAF, testPath)).toBe(currentTestId());
});

/*
 * The two suites below share a leaf title, which is the shape that collapsed onto one identity while the
 * name half carried no ancestors. Each asserts its own identity and that the sibling's differs, so neither
 * depends on the other having run.
 */
describe(FIRST_OPERATION, () => {
  it(REPEATED_LEAF, () => {
    const { testPath } = jestState();
    const mine = emittedIdentity([FIRST_OPERATION], REPEATED_LEAF, testPath);
    const sibling = emittedIdentity([SECOND_OPERATION], REPEATED_LEAF, testPath);

    expect(mine).toBe(currentTestId());
    expect(mine).toContain(FIRST_OPERATION);
    expect(mine).not.toBe(sibling);
  });
});

describe(SECOND_OPERATION, () => {
  it(REPEATED_LEAF, () => {
    const { testPath } = jestState();
    const mine = emittedIdentity([SECOND_OPERATION], REPEATED_LEAF, testPath);
    const sibling = emittedIdentity([FIRST_OPERATION], REPEATED_LEAF, testPath);

    expect(mine).toBe(currentTestId());
    expect(mine).toContain(SECOND_OPERATION);
    expect(mine).not.toBe(sibling);
  });
});
