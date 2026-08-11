/**
 * Contract of `frontend/jest.transform.extensionless.js`: what the four extension-less component modules
 * are called in the artifacts a run produces, and what their compiled form is.
 *
 * The transformer hands ts-jest a synthetic `<path>.tsx` name so a JSX loader can be inferred, and ts-jest
 * writes that name into the source map it emits. Jest passes the emitted map to babel-plugin-istanbul as
 * `inputSourceMap`, and the coverage reporters take each module's identity from the source named there - so
 * a synthetic name reaching the map puts a path that is not in the repository into `coverage-final.json`,
 * `lcov.info`, `cobertura-coverage.xml` and `coverage-summary.json`, the first of which is the Codecov
 * input. These tests pin both halves at once: the name that leaves the transformer is the real
 * extension-less path, and the code that leaves it is still CommonJS with the automatic JSX runtime.
 *
 * @see docs/testing/DECISION-LOG.md - section 12.
 */

import { readFileSync } from 'fs';
import * as path from 'path';

/* eslint-disable @typescript-eslint/no-var-requires */
const transformer = require('../../jest.transform.extensionless.js');

/** The four modules that reach ts-jest under a synthetic name. */
const EXTENSIONLESS_MODULES = ['Dashboard', 'TweetManagement', 'Analytics', 'Configuration'];

/** `//# sourceMappingURL=` comment carrying a JSON source map: media parameters, then payload. */
const INLINE_SOURCE_MAP = /\/\/[#@]\s*sourceMappingURL=data:application\/json([^,]*),(\S+)/;

const ROOT_DIR = path.resolve(__dirname, '..', '..');

/** The transform options Jest supplies, reduced to the members ts-jest reads. */
const transformOptions = {
  config: { cwd: ROOT_DIR, rootDir: ROOT_DIR },
  configString: '{}',
  instrument: false,
  supportsStaticESM: false,
  cacheFS: new Map<string, string>(),
  transformerConfig: {},
};

const realPathOf = (moduleName: string): string => path.join(ROOT_DIR, 'src', 'components', moduleName);

const compile = (moduleName: string): { code: string; sourceMap: Record<string, unknown>; source: string } => {
  const realPath = realPathOf(moduleName);
  const source = readFileSync(realPath, 'utf8');
  const code = String(transformer.process(source, realPath, transformOptions).code);
  const match = INLINE_SOURCE_MAP.exec(code);

  if (match === null) {
    throw new Error(`no inline source map in the compiled output of ${realPath}`);
  }

  const decoded = /;\s*base64\s*$/i.test(match[1])
    ? Buffer.from(match[2], 'base64').toString('utf8')
    : decodeURIComponent(match[2]);

  return { code, sourceMap: JSON.parse(decoded), source };
};

describe('the extension-less transformer names the real module', () => {
  it.each(EXTENSIONLESS_MODULES)('%s: the emitted source map names the extension-less file', (moduleName) => {
    const realPath = realPathOf(moduleName);
    const { sourceMap } = compile(moduleName);

    expect(sourceMap.file).toBe(realPath);
    expect(sourceMap.sources).toEqual([realPath]);
  });

  it.each(EXTENSIONLESS_MODULES)('%s: the synthetic .tsx name appears nowhere in the output', (moduleName) => {
    const { code, sourceMap } = compile(moduleName);

    expect(code).not.toContain(`${realPathOf(moduleName)}.tsx`);
    expect(String(sourceMap.file).endsWith('.tsx')).toBe(false);
    expect((sourceMap.sources as string[]).some((source) => source.endsWith('.tsx'))).toBe(false);
  });
});

describe('the extension-less transformer still compiles what it always compiled', () => {
  it.each(EXTENSIONLESS_MODULES)('%s: emits CommonJS using the automatic JSX runtime', (moduleName) => {
    const { code } = compile(moduleName);

    expect(code).toContain('react/jsx-runtime');
    expect(code).toContain('exports');
    expect(code).not.toMatch(/<[A-Za-z]+[\s/>]/);
  });

  it.each(EXTENSIONLESS_MODULES)('%s: carries the mappings and source text through untouched', (moduleName) => {
    const { sourceMap, source } = compile(moduleName);

    expect(typeof sourceMap.mappings).toBe('string');
    expect((sourceMap.mappings as string).length).toBeGreaterThan(0);
    expect(sourceMap.sourcesContent).toEqual([source]);
  });
});

describe('the extension-less transformer keeps its own cache namespace', () => {
  it('returns a stable key for one input and a different key for another', () => {
    const realPath = realPathOf('Dashboard');
    const source = readFileSync(realPath, 'utf8');

    const first = transformer.getCacheKey(source, realPath, transformOptions);
    const second = transformer.getCacheKey(source, realPath, transformOptions);
    const edited = transformer.getCacheKey(`${source}\nexport const added = 1;\n`, realPath, transformOptions);

    expect(typeof first).toBe('string');
    expect(second).toBe(first);
    expect(edited).not.toBe(first);
  });
});
