/**
 * Jest transformer for the extension-less component modules.
 *
 * Contract of every `process` call:
 *
 * 1. ts-jest compiles the source text unchanged, under the synthetic name
 *    `<sourcePath>.tsx`, from which it infers its loader.
 * 2. The synthetic name is never returned to Jest's module resolver, and never
 *    survives in the emitted source map: `file` and every `sources` entry naming
 *    it are restored to the real extension-less path, in an inline data-URL
 *    payload and in a separate `map` field alike.
 * 3. The compiled code, `mappings`, `names` and `sourcesContent` are returned
 *    exactly as ts-jest produced them, so every coverage count derived from the
 *    map is unchanged.
 *
 * Resolving these modules is a separate concern, handled by `moduleNameMapper`
 * and `moduleFileExtensions` in `frontend/jest.config.js`.
 *
 * @see https://jestjs.io/docs/code-transformation#writing-custom-transformers
 * @see frontend/src/components/Dashboard.test.tsx - one of the four component
 *   suites this transformer makes compilable.
 * @see docs/testing/DECISION-LOG.md - rows D30-D32 and D138-D140.
 */

'use strict';

const { TsJestTransformer } = require('ts-jest');

const SYNTHETIC_EXTENSION = '.tsx';

/*
 * Namespace appended to the inner cache key. Bump it whenever `process` changes
 * what it returns: an entry written before the change is otherwise reused.
 *
 * @see docs/testing/DECISION-LOG.md - row D139.
 */
const CACHE_KEY_SUFFIX = ':extensionless:real-source-identity';

/* `//# sourceMappingURL=` comment carrying a JSON source map: prefix, media parameters, payload. */
const INLINE_SOURCE_MAP_PATTERN =
  /(\/\/[#@]\s*sourceMappingURL=data:application\/json)([^,]*),(\S+)/g;

/*
 * Compiler options passed inline to ts-jest; no tsconfig file is read. Every
 * entry but `isolatedModules` mirrors the primary transform in
 * `frontend/jest.config.js`.
 *
 * @see docs/testing/DECISION-LOG.md - row D32.
 */
const TSCONFIG = {
  jsx: 'react-jsx',
  module: 'commonjs',
  esModuleInterop: true,
  allowJs: true,
  target: 'ES2020',
  isolatedModules: true,
};

/* One inner transformer, shared by every call in this worker. */
const inner = new TsJestTransformer({
  tsconfig: TSCONFIG,
  diagnostics: false,
});

if (typeof inner.process !== 'function' || typeof inner.getCacheKey !== 'function') {
  throw new TypeError(
    'jest.transform.extensionless.js requires TsJestTransformer#process and #getCacheKey, ' +
      'which the installed ts-jest does not expose. Expected the version pinned in ' +
      'frontend/package.json ("ts-jest": "29.4.12"). Run `npm install` in frontend/ to restore it.'
  );
}

/**
 * Replaces the synthetic path with the real one, keeping the separator style of
 * the value being replaced. Any other value is returned untouched.
 *
 * @param {unknown} value A `file` or `sources` entry of an emitted source map.
 * @param {string} syntheticPath The name handed to ts-jest.
 * @param {string} realPath Absolute path of the extension-less module.
 * @returns {unknown} `realPath` when `value` names the synthetic file.
 */
function restoreSourcePath(value, syntheticPath, realPath) {
  if (typeof value !== 'string') {
    return value;
  }

  const toPosix = (candidate) => candidate.split('\\').join('/');

  if (toPosix(value) !== toPosix(syntheticPath)) {
    return value;
  }

  return value.includes('\\') ? realPath : toPosix(realPath);
}

/**
 * Rewrites the `file` and `sources` entries of a source map object. `mappings`,
 * `names` and `sourcesContent` are carried over untouched, so the positions the
 * map describes - and therefore every coverage count derived from it - are
 * unchanged.
 *
 * @param {object} sourceMap A decoded source map.
 * @param {string} syntheticPath The name handed to ts-jest.
 * @param {string} realPath Absolute path of the extension-less module.
 * @returns {object} A copy naming the real module.
 */
function restoreSourceMap(sourceMap, syntheticPath, realPath) {
  const restored = { ...sourceMap };

  restored.file = restoreSourcePath(restored.file, syntheticPath, realPath);

  if (Array.isArray(restored.sources)) {
    restored.sources = restored.sources.map((source) =>
      restoreSourcePath(source, syntheticPath, realPath)
    );
  }

  return restored;
}

/**
 * Rewrites every inline source map embedded in compiled code. A payload that
 * cannot be decoded or parsed is left exactly as it was.
 *
 * @param {string} code Compiled code as ts-jest emitted it.
 * @param {string} syntheticPath The name handed to ts-jest.
 * @param {string} realPath Absolute path of the extension-less module.
 * @returns {string} The code with its inline maps naming the real module.
 */
function restoreInlineSourceMaps(code, syntheticPath, realPath) {
  return code.replace(INLINE_SOURCE_MAP_PATTERN, (comment, prefix, mediaParameters, payload) => {
    const isBase64 = /;\s*base64\s*$/i.test(mediaParameters);
    let sourceMap;

    try {
      sourceMap = JSON.parse(
        isBase64
          ? Buffer.from(payload, 'base64').toString('utf8')
          : decodeURIComponent(payload)
      );
    } catch (error) {
      return comment;
    }

    const restored = JSON.stringify(restoreSourceMap(sourceMap, syntheticPath, realPath));

    return (
      prefix +
      mediaParameters +
      ',' +
      (isBase64 ? Buffer.from(restored, 'utf8').toString('base64') : encodeURIComponent(restored))
    );
  });
}

/**
 * Restores the real module identity in whichever shape the inner transformer
 * returned - a bare code string, or an object carrying `code` and optionally a
 * `map` as an object or a JSON string. The shape itself is preserved.
 *
 * @param {{code: string, map?: unknown}|string} result The inner result.
 * @param {string} syntheticPath The name handed to ts-jest.
 * @param {string} realPath Absolute path of the extension-less module.
 * @returns {{code: string, map?: unknown}|string} The result, naming the real module.
 */
function restoreModuleIdentity(result, syntheticPath, realPath) {
  if (typeof result === 'string') {
    return restoreInlineSourceMaps(result, syntheticPath, realPath);
  }

  if (result === null || typeof result !== 'object') {
    return result;
  }

  const restored = { ...result };

  if (typeof restored.code === 'string') {
    restored.code = restoreInlineSourceMaps(restored.code, syntheticPath, realPath);
  }

  if (typeof restored.map === 'string') {
    try {
      restored.map = JSON.stringify(
        restoreSourceMap(JSON.parse(restored.map), syntheticPath, realPath)
      );
    } catch (error) {
      /* Leave an unparseable map exactly as the inner transformer emitted it. */
    }
  } else if (restored.map !== null && typeof restored.map === 'object') {
    restored.map = restoreSourceMap(restored.map, syntheticPath, realPath);
  }

  return restored;
}

/**
 * Compiles extension-less TypeScript JSX through ts-jest, then restores the real
 * module identity in the emitted source map.
 *
 * @param {string} sourceText Contents Jest read from `sourcePath`.
 * @param {string} sourcePath Absolute path of the extension-less module.
 * @param {object} transformOptions Jest transform options.
 * @returns {{code: string, map?: unknown}|string} The inner result, naming `sourcePath`.
 */
function process(sourceText, sourcePath, transformOptions) {
  const syntheticPath = sourcePath + SYNTHETIC_EXTENSION;

  return restoreModuleIdentity(
    inner.process(sourceText, syntheticPath, transformOptions),
    syntheticPath,
    sourcePath
  );
}

/**
 * Cache key for an extension-less module, namespaced by `CACHE_KEY_SUFFIX`.
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
