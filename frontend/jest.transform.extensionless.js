/**
 * Jest transformer for the extension-less component modules.
 *
 * Delegates every call to ts-jest under the synthetic name `<sourcePath>.tsx`,
 * from which ts-jest infers its loader, and passes the source text through
 * unchanged. The synthetic name travels inward to ts-jest only; it is never
 * returned to Jest's module resolver, so it affects loader inference and
 * nothing else. Resolving these modules is a separate concern this file does
 * not address.
 *
 * @see https://jestjs.io/docs/code-transformation#writing-custom-transformers
 */

'use strict';

const { TsJestTransformer } = require('ts-jest');

const SYNTHETIC_EXTENSION = '.tsx';

const CACHE_KEY_SUFFIX = ':extensionless';

/* Compiler options passed inline to ts-jest; no tsconfig file is read. */
const TSCONFIG = {
  jsx: 'react-jsx',
  module: 'commonjs',
  esModuleInterop: true,
  allowJs: true,
  target: 'ES2020',
};

/* One inner transformer, shared by every call in this worker. */
const inner = new TsJestTransformer({
  tsconfig: TSCONFIG,
  diagnostics: false,
  isolatedModules: true,
});

if (typeof inner.process !== 'function' || typeof inner.getCacheKey !== 'function') {
  throw new TypeError(
    'jest.transform.extensionless.js requires TsJestTransformer#process and #getCacheKey, ' +
      'which the installed ts-jest does not expose. Expected the version pinned in ' +
      'frontend/package.json ("ts-jest": "29.4.12"). Run `npm install` in frontend/ to restore it.'
  );
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
  return inner.process(sourceText, sourcePath + SYNTHETIC_EXTENSION, transformOptions);
}

/**
 * Cache key for an extension-less module, suffixed with `:extensionless`.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {string} Namespaced cache key.
 */
function getCacheKey(sourceText, sourcePath, transformOptions) {
  const innerKey = inner.getCacheKey(sourceText, sourcePath + SYNTHETIC_EXTENSION, transformOptions);

  return String(innerKey) + CACHE_KEY_SUFFIX;
}

module.exports = {
  process,
  getCacheKey,
};
