/**
 * Jest transformer for the extension-less component modules.
 *
 * `src/components/Dashboard`, `src/components/TweetManagement`,
 * `src/components/Analytics` and `src/components/Configuration` are files that
 * carry no extension, and their contents are TypeScript JSX. ts-jest selects a
 * loader from the file NAME it is handed, so an extension-less name resolves to
 * no loader and the source is returned uncompiled.
 *
 * This transformer delegates every call to ts-jest under a synthetic
 * `<sourcePath>.tsx` name while passing the real source text through unchanged.
 * The synthetic name travels inward to ts-jest only; it is never returned to
 * Jest's module resolver. Resolution of these modules is handled separately by
 * `moduleNameMapper` and `moduleFileExtensions` in `jest.config.js`, which is
 * also what routes the four paths here via its secondary `transform` entry.
 *
 * Decision rationale for this module lives in `docs/testing/DECISION-LOG.md`.
 *
 * @see https://jestjs.io/docs/code-transformation#writing-custom-transformers
 */

'use strict';

const { createHash } = require('crypto');
const { TsJestTransformer } = require('ts-jest');

/* Marker: name handed inward to ts-jest for loader inference. */
const SYNTHETIC_EXTENSION = '.tsx';

/* Marker: namespace separating this transformer's cache entries from the primary ts-jest transformer's. */
const CACHE_KEY_SUFFIX = ':extensionless';

/* Marker: ts-jest export-surface guard. */
if (typeof TsJestTransformer !== 'function') {
  throw new TypeError(
    'jest.transform.extensionless.js requires the "TsJestTransformer" class exported by ts-jest, ' +
      'but the installed ts-jest does not export it. Expected the version pinned in ' +
      'frontend/package.json ("ts-jest": "29.4.12"). Run `npm install` in frontend/ to restore it.'
  );
}

/* Marker: inline compiler options; mirrored by the primary transform in jest.config.js. */
const TSCONFIG = {
  jsx: 'react-jsx',
  module: 'commonjs',
  esModuleInterop: true,
  allowJs: true,
  target: 'ES2020',
};

/* Marker: single inner transformer shared by every call in this worker. */
const inner = new TsJestTransformer({
  tsconfig: TSCONFIG,
  diagnostics: false,
  isolatedModules: true,
});

/**
 * Builds the synthetic name for a real, extension-less source path.
 *
 * @param {string} sourcePath Absolute path Jest is transforming.
 * @returns {string} `sourcePath` suffixed with `.tsx`.
 * @throws {TypeError} When `sourcePath` is not a non-empty string.
 */
function toSyntheticPath(sourcePath) {
  if (typeof sourcePath !== 'string' || sourcePath.length === 0) {
    throw new TypeError(
      'jest.transform.extensionless.js expected a non-empty source path, received ' +
        (typeof sourcePath === 'string' ? 'an empty string' : typeof sourcePath) +
        '.'
    );
  }

  return sourcePath + SYNTHETIC_EXTENSION;
}

/**
 * Validates the source text Jest supplies before it is handed to ts-jest.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path the text was read from.
 * @throws {TypeError} When `sourceText` is not a string.
 */
function assertSourceText(sourceText, sourcePath) {
  if (typeof sourceText !== 'string') {
    throw new TypeError(
      'jest.transform.extensionless.js expected string source text for "' +
        sourcePath +
        '", received ' +
        typeof sourceText +
        '.'
    );
  }
}

/**
 * Fallback cache key used only when the inner transformer exposes no
 * `getCacheKey`. Mirrors the inputs Jest itself hashes, plus the synthetic name.
 *
 * @param {string} sourceText Contents being transformed.
 * @param {string} syntheticPath Synthetic `.tsx` name for the source.
 * @param {object} [transformOptions] Options Jest passed to the transformer.
 * @returns {string} Hex digest.
 */
function fallbackCacheKey(sourceText, syntheticPath, transformOptions) {
  const options = transformOptions || {};

  return createHash('sha1')
    .update(sourceText)
    .update('\u0000')
    .update(syntheticPath)
    .update('\u0000')
    .update(typeof options.configString === 'string' ? options.configString : '')
    .update('\u0000')
    .update(options.instrument ? 'instrument' : '')
    .update('\u0000')
    .update(options.supportsStaticESM ? 'esm' : 'cjs')
    .digest('hex');
}

/**
 * Compiles extension-less TypeScript JSX through ts-jest.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {{code: string, map?: unknown}|string} The inner result, unaltered.
 */
function process(sourceText, sourcePath, transformOptions) {
  const syntheticPath = toSyntheticPath(sourcePath);
  assertSourceText(sourceText, sourcePath);

  return inner.process(sourceText, syntheticPath, transformOptions);
}

/**
 * Asynchronous counterpart of {@link process}.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {Promise<{code: string, map?: unknown}|string>} The inner result, unaltered.
 */
async function processAsync(sourceText, sourcePath, transformOptions) {
  const syntheticPath = toSyntheticPath(sourcePath);
  assertSourceText(sourceText, sourcePath);

  if (typeof inner.processAsync !== 'function') {
    return inner.process(sourceText, syntheticPath, transformOptions);
  }

  return inner.processAsync(sourceText, syntheticPath, transformOptions);
}

/**
 * Cache key for an extension-less module, namespaced so Jest never serves an
 * artifact produced by the primary ts-jest transformer to this one.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {string} Namespaced cache key.
 */
function getCacheKey(sourceText, sourcePath, transformOptions) {
  const syntheticPath = toSyntheticPath(sourcePath);
  assertSourceText(sourceText, sourcePath);

  const innerKey =
    typeof inner.getCacheKey === 'function'
      ? inner.getCacheKey(sourceText, syntheticPath, transformOptions)
      : fallbackCacheKey(sourceText, syntheticPath, transformOptions);

  return String(innerKey) + CACHE_KEY_SUFFIX;
}

/**
 * Asynchronous counterpart of {@link getCacheKey}.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {Promise<string>} Namespaced cache key.
 */
async function getCacheKeyAsync(sourceText, sourcePath, transformOptions) {
  const syntheticPath = toSyntheticPath(sourcePath);
  assertSourceText(sourceText, sourcePath);

  if (typeof inner.getCacheKeyAsync !== 'function') {
    return getCacheKey(sourceText, sourcePath, transformOptions);
  }

  const innerKey = await inner.getCacheKeyAsync(sourceText, syntheticPath, transformOptions);

  return String(innerKey) + CACHE_KEY_SUFFIX;
}

module.exports = {
  process,
  processAsync,
  getCacheKey,
  getCacheKeyAsync,
};
