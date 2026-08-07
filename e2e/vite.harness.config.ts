/**
 * Vite dev-server configuration for the Playwright end-to-end harness.
 *
 * Serves the real modules under `frontend/src` through an HTML entry owned
 * entirely by `e2e/harness`. Nothing under `frontend/` or `backend/` is created,
 * modified or renamed; those files are read only for their source text.
 *
 * Dev-server only. Playwright's `webServer` runs `vite`, never `vite build`.
 *
 * Rationale for every decision in this file is recorded in
 * `docs/testing/DECISION-LOG.md`.
 */

import fs from 'node:fs';
import path from 'node:path';
import { defineConfig, transformWithEsbuild, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

/* -------------------------------------------------------------------------- */
/* Paths                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * `e2e/package.json` declares no `type`, so Vite bundles this config to CJS and
 * `__dirname` is defined. Every path below derives from `__dirname`; none reads
 * `process.cwd()`.
 */
const HERE = __dirname;
const REPO_ROOT = path.resolve(HERE, '..');
const FRONTEND = path.join(REPO_ROOT, 'frontend');
const FRONTEND_SRC = path.join(FRONTEND, 'src');
const FRONTEND_MODULES = path.join(FRONTEND, 'node_modules');
const HARNESS = path.join(HERE, 'harness');
const STUBS = path.join(HARNESS, 'stubs');

/* -------------------------------------------------------------------------- */
/* Module tables                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Component modules that exist on disk as extension-less FILES, not directories.
 * No loader can be inferred from their path.
 *
 * To extend the harness with another such component, add its file name here.
 */
const EXTENSIONLESS_COMPONENTS = [
  'Dashboard',
  'TweetManagement',
  'Analytics',
  'Configuration',
] as const;

/**
 * Module specifiers the frontend imports that have no implementation anywhere in
 * the repository, mapped to their stand-ins under `e2e/harness/stubs`.
 *
 * Keys are paths under `frontend/src` without an extension. Each redirect is
 * applied only while the real module is absent.
 *
 * To stub another missing module, add one entry here and create the matching
 * file under `e2e/harness/stubs`.
 */
const STUB_MODULES: Record<string, string> = {
  'services/analyticsService': 'analyticsService.ts',
  'services/configService': 'configService.ts',
  'schema/configSchema': 'configSchema.ts',
};

/**
 * Named exports the frontend imports but never declares. Each entry is appended
 * to the end of the real module's source text; nothing in that text is rewritten.
 *
 * Keys are paths under `frontend/src` without an extension. Values map an export
 * name to an expression evaluated in that module's own scope.
 *
 * To supply another missing binding, add one entry here.
 */
const COMPAT_EXPORTS: Record<string, Record<string, string>> = {
  'services/api': {
    api: 'axios',
    setupInterceptors: '() => {}',
  },
  'services/twitterService': {
    getTweets: 'undefined',
  },
  'components/TweetManagement': {
    TweetCard: 'undefined',
  },
};

/**
 * Bare specifiers the frontend imports that no installed package provides,
 * mapped to paths under `frontend/src`.
 *
 * This table is the single source of truth for both the resolver below and the
 * matching `resolve.alias` entries.
 */
const BARE_MODULE_SPECIFIERS: Record<string, string> = {
  'app/services/api': 'services/api',
  'app/schema/tweet': 'schema/tweetSchema',
  'app/schema/user': 'schema/userSchema',
};

/**
 * Runtime packages the harness graph imports. Each is pinned to an absolute path
 * under `frontend/node_modules`, which is the only copy of them on disk.
 *
 * This table drives both `resolve.alias` and `optimizeDeps.include`.
 *
 * Ordered longest specifier first: a shorter package name would otherwise claim a
 * longer one's subpath.
 *
 * To add a runtime dependency to the harness, add one entry here.
 */
const FRONTEND_PACKAGES = [
  'react-dom/client',
  'react/jsx-dev-runtime',
  'react/jsx-runtime',
  'react-router-dom',
  '@reduxjs/toolkit',
  'react-redux',
  'react-dom',
  'react',
  'axios',
  'chart.js',
] as const;

/** Packages that must resolve to exactly one copy across the whole graph. */
const DEDUPED_PACKAGES = [
  'react',
  'react-dom',
  'react-redux',
  'react-router-dom',
  '@reduxjs/toolkit',
] as const;

/**
 * esbuild TypeScript options, serialised to a string.
 *
 * Vite skips its own tsconfig lookup entirely when `tsconfigRaw` is a string, and
 * performs it for every `ts`/`tsx` loader when it is an object. The string form is
 * therefore required here, and is passed to each `transformWithEsbuild` call as
 * well as to `esbuild` below.
 */
const TSCONFIG_RAW = JSON.stringify({
  compilerOptions: {
    target: 'ES2020',
    jsx: 'react-jsx',
    esModuleInterop: true,
    allowSyntheticDefaultImports: true,
    useDefineForClassFields: false,
  },
});

/* -------------------------------------------------------------------------- */
/* Virtual module registry                                                    */
/* -------------------------------------------------------------------------- */

/** Virtual id prefix for the extension-less component files. */
const EXTLESS_PREFIX = '\0extless:';

/** Virtual id prefix for real modules served with appended compatibility exports. */
const COMPAT_PREFIX = '\0compat:';

/** A real module served through a virtual id. */
interface VirtualModule {
  /** Absolute path of the real file whose source text is served. */
  realPath: string;
  /** File name handed to esbuild, which is what fixes the loader. */
  transformFilename: string;
  /** esbuild loader for the source text. */
  loader: 'ts' | 'tsx';
  /** Export name to expression, appended to the source text. */
  compat: Record<string, string>;
}

/** Virtual id to the module it serves. */
const virtualModules = new Map<string, VirtualModule>();

/** Normalised module key to the virtual id that replaces it. */
const virtualIdByModuleKey = new Map<string, string>();

/** Normalised module key to the stub that replaces it while the real module is absent. */
const stubsByModuleKey = new Map<string, { relative: string; stubPath: string }>();

/**
 * Forward-slash form of a path. Vite normalises separators on every id it hands
 * back, so virtual ids are built in this form to begin with.
 */
function toPosixPath(candidate: string): string {
  return candidate.replace(/\\/g, '/');
}

/**
 * Separator- and case-normalised form used as the key for every lookup. Vite's
 * alias replacement is a plain string substitution, so ids reach this plugin with
 * mixed separators on Windows.
 */
function normalizeKey(candidate: string): string {
  const slashed = toPosixPath(candidate);
  return process.platform === 'win32' ? slashed.toLowerCase() : slashed;
}

/** Drops a trailing Vite query such as `?import`. */
function withoutQuery(id: string): string {
  const marker = id.indexOf('?');
  return marker === -1 ? id : id.slice(0, marker);
}

/**
 * Absolute path of the real module for a `frontend/src`-relative path, trying
 * the extension-less file first, then `.ts` and `.tsx`. Returns `null` when no
 * such file exists.
 */
function findRealModule(relative: string): string | null {
  for (const extension of ['', '.ts', '.tsx']) {
    const candidate = path.join(FRONTEND_SRC, relative + extension);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return null;
}

/** Registers one real module to be served through a virtual id. */
function registerVirtualModule(relative: string, prefix: string, loader: 'ts' | 'tsx'): void {
  const realPath = findRealModule(relative);
  if (realPath === null) {
    return;
  }

  // An extension-less file is handed to esbuild under a synthetic `.tsx` name,
  // which is what lets the loader be inferred.
  const isExtensionless = path.extname(realPath) === '';
  const transformFilename = isExtensionless ? `${realPath}.${loader}` : realPath;

  const virtualId = prefix + toPosixPath(realPath);
  virtualModules.set(normalizeKey(virtualId), {
    realPath,
    transformFilename,
    loader,
    compat: COMPAT_EXPORTS[relative] ?? {},
  });

  // Both spellings are registered: the alias-expanded path without an extension
  // and the fully qualified path of the file on disk.
  virtualIdByModuleKey.set(normalizeKey(path.join(FRONTEND_SRC, relative)), virtualId);
  virtualIdByModuleKey.set(normalizeKey(realPath), virtualId);
}

for (const name of EXTENSIONLESS_COMPONENTS) {
  registerVirtualModule(`components/${name}`, EXTLESS_PREFIX, 'tsx');
}

for (const relative of Object.keys(COMPAT_EXPORTS)) {
  const alreadyRegistered = virtualIdByModuleKey.has(normalizeKey(path.join(FRONTEND_SRC, relative)));
  if (!alreadyRegistered) {
    registerVirtualModule(relative, COMPAT_PREFIX, 'ts');
  }
}

for (const [relative, stubFile] of Object.entries(STUB_MODULES)) {
  stubsByModuleKey.set(normalizeKey(path.join(FRONTEND_SRC, relative)), {
    relative,
    stubPath: path.join(STUBS, stubFile),
  });
}

/* -------------------------------------------------------------------------- */
/* Resolver plugin                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Every spelling under which an import may reach this plugin, normalised for
 * comparison against the registries above.
 *
 * `resolve.alias` is applied before `enforce: 'pre'` plugins and re-enters the
 * resolver with the rewritten id, and `vite:resolve` runs after them, so an
 * import arrives here either bare, `@/`-prefixed, already absolute, or still
 * relative.
 */
function candidateModuleKeys(id: string, importer: string | undefined): string[] {
  const keys: string[] = [];

  const bareTarget = BARE_MODULE_SPECIFIERS[id];
  if (bareTarget !== undefined) {
    keys.push(normalizeKey(path.join(FRONTEND_SRC, bareTarget)));
  }

  if (id.startsWith('@/')) {
    keys.push(normalizeKey(path.join(FRONTEND_SRC, id.slice(2))));
  }

  if (path.isAbsolute(id)) {
    keys.push(normalizeKey(path.normalize(id)));
  } else if (id.startsWith('.') && importer !== undefined) {
    // A virtual importer carries its real path after the prefix.
    const importerPath = withoutQuery(importer).replace(/^\0[^:]*:/, '');
    if (path.isAbsolute(importerPath)) {
      keys.push(normalizeKey(path.resolve(path.dirname(importerPath), id)));
    }
  }

  return keys;
}

/** Source text appended to a real module to supply the exports it never declares. */
function compatExportTail(compat: Record<string, string>): string {
  const names = Object.keys(compat);
  if (names.length === 0) {
    return '';
  }

  // A prefixed local keeps the appended declaration from colliding with an
  // identically named binding the module already imports.
  const declarations = names.map((name) => {
    const local = `__harnessCompat_${name}`;
    return `const ${local} = ${compat[name]};\nexport { ${local} as ${name} };`;
  });

  return `\n\n/* appended by e2e/vite.harness.config.ts */\n${declarations.join('\n')}\n`;
}

/**
 * Resolves the frontend sources that no bundler can load as written:
 *
 * - the extension-less component files, through a NUL-prefixed virtual id whose
 *   `load` hook hands the source text to esbuild under a synthetic `.tsx` name;
 * - the module specifiers that have no implementation, to the harness stubs,
 *   only while the real module is absent;
 * - the real modules whose importers expect exports they never declare, through a
 *   NUL-prefixed virtual id that appends those exports to the real source text.
 */
function harnessSourceResolver(): Plugin {
  return {
    name: 'harness-source-resolver',
    enforce: 'pre',

    resolveId(id, importer) {
      // Already claimed; returning the id keeps the prefix from being stacked.
      if (id.startsWith('\0')) {
        return virtualModules.has(normalizeKey(withoutQuery(id))) ? id : null;
      }

      for (const key of candidateModuleKeys(id, importer)) {
        const virtualId = virtualIdByModuleKey.get(key);
        if (virtualId !== undefined) {
          return virtualId;
        }

        const stub = stubsByModuleKey.get(key);
        if (stub !== undefined && findRealModule(stub.relative) === null) {
          return stub.stubPath;
        }
      }

      return null;
    },

    async load(id) {
      const virtualModule = virtualModules.get(normalizeKey(withoutQuery(id)));
      if (virtualModule === undefined) {
        return null;
      }

      const source = fs.readFileSync(virtualModule.realPath, 'utf8');
      const transformed = await transformWithEsbuild(
        source + compatExportTail(virtualModule.compat),
        virtualModule.transformFilename,
        {
          loader: virtualModule.loader,
          jsx: 'automatic',
          tsconfigRaw: TSCONFIG_RAW,
        },
      );

      return { code: transformed.code, map: transformed.map };
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Configuration                                                              */
/* -------------------------------------------------------------------------- */

export default defineConfig({
  root: HARNESS,

  // Supplies the history fallback the repository has no configuration for, so
  // every client route serves the harness entry.
  appType: 'spa',

  // The custom resolver carries `enforce: 'pre'` and so runs before the React
  // plugin regardless of order here.
  plugins: [harnessSourceResolver(), react()],

  server: {
    host: '127.0.0.1',
    port: 4173,
    // Fail the start on a port collision; do not select another port.
    strictPort: true,
    fs: {
      // The root is `e2e/harness` and `e2e/package.json` is the nearest manifest,
      // so Vite scopes filesystem access to `e2e/` unless the repository root is
      // named here. Every module under `frontend/src` is served through it.
      allow: [REPO_ROOT],
    },
  },

  // The default cache directory resolves against the root, which has no
  // `node_modules`.
  cacheDir: path.join(HERE, 'node_modules', '.vite'),

  // The dev-server log is the harness's health signal. Playwright pipes this
  // output, and it is kept intact and unscrolled.
  logLevel: 'info',
  clearScreen: false,

  esbuild: {
    tsconfigRaw: TSCONFIG_RAW,
  },

  resolve: {
    // An ordered array: the first matching entry wins.
    alias: [
      ...FRONTEND_PACKAGES.map((specifier) => ({
        find: specifier,
        replacement: path.join(FRONTEND_MODULES, specifier),
      })),
      ...Object.entries(BARE_MODULE_SPECIFIERS).map(([specifier, target]) => ({
        find: specifier,
        replacement: path.join(FRONTEND_SRC, target),
      })),
      { find: '@', replacement: FRONTEND_SRC },
    ],
    dedupe: [...DEDUPED_PACKAGES],
  },

  optimizeDeps: {
    include: [...FRONTEND_PACKAGES],
  },

  // `frontend/src/services/api.ts` reads `process.env` at module scope, which a
  // browser does not provide. The dev server installs these entries as globals
  // through `@vite/env`, walking each key and assigning in declaration order, so
  // the broadest key comes first and the narrowest last.
  //
  // `REACT_APP_API_BASE_URL` resolves to the `undefined` literal, which keeps the
  // base URL that production computes today.
  define: {
    'process.env': '({})',
    'process.env.NODE_ENV': JSON.stringify('development'),
    'process.env.REACT_APP_API_BASE_URL': 'undefined',
  },
});
