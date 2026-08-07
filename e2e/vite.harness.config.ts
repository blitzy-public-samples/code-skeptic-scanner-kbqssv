/**
 * Vite dev-server configuration for the Playwright end-to-end harness.
 *
 * Serves the real modules under `frontend/src` through an HTML entry owned
 * entirely by `e2e/harness`. Nothing under `frontend/` or `backend/` is created,
 * modified or renamed; those files are read only for their source text.
 *
 * Configures the dev server only: it declares no `build` options.
 */

import fs from 'node:fs';
import path from 'node:path';
import { defineConfig, transformWithEsbuild, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

/* -------------------------------------------------------------------------- */
/* Paths                                                                      */
/* -------------------------------------------------------------------------- */

/** Every path below derives from `__dirname`; none reads `process.cwd()`. */
const HERE = __dirname;
const REPO_ROOT = path.resolve(HERE, '..');
const FRONTEND = path.join(REPO_ROOT, 'frontend');
const FRONTEND_SRC = path.join(FRONTEND, 'src');
const FRONTEND_MODULES = path.join(FRONTEND, 'node_modules');
const HARNESS = path.join(HERE, 'harness');
const STUBS = path.join(HARNESS, 'stubs');
const CACHE_DIR = path.join(HERE, 'node_modules', '.vite');

/**
 * Client runtime of the Vite installation that serves the harness, holding
 * `client.mjs` and `env.mjs`.
 *
 * `/@vite/client` opens with `import "/@fs/<this directory>/env.mjs"`. `/main.tsx`,
 * `/@react-refresh` and the `index.html` preamble each import `/@vite/client`, which
 * places this directory in the dependency chain of every module script in the
 * document.
 */
const VITE_CLIENT_DIR = path.join(HERE, 'node_modules', 'vite', 'dist', 'client');

/* -------------------------------------------------------------------------- */
/* Module tables                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Component modules that exist on disk as extension-less FILES, not directories.
 *
 * Add a file name to extend the harness.
 */
const EXTENSIONLESS_COMPONENTS = [
  'Dashboard',
  'TweetManagement',
  'Analytics',
  'Configuration',
] as const;

/**
 * Module specifiers with no implementation in the repository, mapped to their
 * stand-ins under `e2e/harness/stubs`.
 *
 * Keys are paths under `frontend/src` without an extension. Each redirect applies
 * only while the real module is absent.
 *
 * Add an entry plus the matching file under `e2e/harness/stubs` to extend.
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
 * A missing named export is a link-time error under native ESM, so every entry
 * here exists to let the importing module load. Each value is `undefined`, which
 * is the value the same import already has under Jest and CommonJS, so the
 * importer reaches the same branch in the harness as it does everywhere else.
 *
 * Keys are paths under `frontend/src` without an extension. Values map an export
 * name to an expression evaluated in that module's own scope.
 *
 * Add an entry to extend.
 */
const COMPAT_EXPORTS: Record<string, Record<string, string>> = {
  'services/api': {
    api: 'undefined',
  },
  'services/twitterService': {
    getTweets: 'undefined',
  },
  'components/TweetManagement': {
    TweetCard: 'undefined',
  },
};

/**
 * Bare specifiers no installed package provides, mapped to paths under
 * `frontend/src`. Drives the resolver below and the matching `resolve.alias`
 * entries.
 */
const BARE_MODULE_SPECIFIERS: Record<string, string> = {
  'app/services/api': 'services/api',
  'app/schema/tweet': 'schema/tweetSchema',
  'app/schema/user': 'schema/userSchema',
};

/**
 * Runtime packages the harness graph imports. Each is pinned to an absolute path
 * under `frontend/node_modules`, which is the harness's canonical resolution
 * location for them.
 *
 * Ordered longest specifier first; `resolve.alias` matches in order.
 *
 * Add an entry to extend.
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

/* -------------------------------------------------------------------------- */
/* Dev-server file access                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The only directories this dev server may read over `/@fs/`: the harness itself,
 * which contains `harness/stubs`; the pre-bundle cache, from which the optimised
 * deps are served; the Vite client runtime, from which the dev client is served;
 * and the frontend sources and package tree the aliases resolve to.
 *
 * The Vite root is `e2e/harness` and the nearest manifest is `e2e/package.json`,
 * so `server.fs.strict` scopes access to `e2e/` unless the directories holding the
 * graph are named here. `harnessFilesystemGuard` below checks this same list through
 * `isWithinAllowedRoot`, and it runs ahead of the Vite middleware that exempts the
 * client runtime.
 *
 * Nothing outside these five is part of the harness graph.
 *
 * To serve another directory, add one entry here.
 */
const ALLOWED_SERVE_ROOTS = [
  HARNESS,
  CACHE_DIR,
  VITE_CLIENT_DIR,
  FRONTEND_SRC,
  FRONTEND_MODULES,
] as const;

/**
 * Sensitive file names refused inside the allowed roots. Replaces Vite's default
 * deny list, whose three entries are the first three here.
 */
const DENIED_FILE_PATTERNS = [
  '.env',
  '.env.*',
  '*.{crt,pem}',
  '*.{key,pfx,p12,cer,cert,jks,keystore}',
  '.npmrc',
  '.netrc',
  'id_rsa*',
  '*.local',
  '**/.git/**',
] as const;

/** The `DENIED_FILE_PATTERNS` names, applied to a resolved absolute path. */
const DENIED_PATH_EXPRESSION =
  /(^|[\\/])(\.env(\.[^\\/]*)?|\.npmrc|\.netrc|id_rsa[^\\/]*|\.git)([\\/]|$)|\.(crt|pem|key|pfx|p12|cer|cert|jks|keystore|local)$/i;

/** URL prefix under which Vite serves a file by absolute path. */
const FS_URL_PREFIX = '/@fs/';

/** Dev-server endpoint that spawns a local editor process; the harness never uses it. */
const OPEN_IN_EDITOR_PATH = '/__open-in-editor';

/**
 * esbuild TypeScript options in string form, which suppresses Vite's own tsconfig
 * lookup. Passed to every `transformWithEsbuild` call and to `esbuild` below.
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

/** Forward-slash form of a path, the form every virtual id is built in. */
function toPosixPath(candidate: string): string {
  return candidate.replace(/\\/g, '/');
}

/**
 * Separator- and case-normalised key for every lookup below. Ids reach this
 * plugin with mixed separators on Windows.
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

  // Marker: an extension-less file is handed to esbuild under a synthetic
  // `<realPath>.<loader>` name, which is what fixes its loader.
  const isExtensionless = path.extname(realPath) === '';
  const transformFilename = isExtensionless ? `${realPath}.${loader}` : realPath;

  const virtualId = prefix + toPosixPath(realPath);
  virtualModules.set(normalizeKey(virtualId), {
    realPath,
    transformFilename,
    loader,
    compat: COMPAT_EXPORTS[relative] ?? {},
  });

  // Marker: two spellings registered - the alias-expanded extension-less path and
  // the fully qualified path of the file on disk.
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
 * comparison against the registries above: bare, `@/`-prefixed, already absolute,
 * or relative to its importer.
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

  // Marker: prefixed locals cannot collide with a binding the module already has.
  const declarations = names.map((name) => {
    const local = `__harnessCompat_${name}`;
    return `const ${local} = ${compat[name]};\nexport { ${local} as ${name} };`;
  });

  return `\n\n/* appended by e2e/vite.harness.config.ts */\n${declarations.join('\n')}\n`;
}

/**
 * Resolves three classes of frontend source:
 *
 * - the extension-less component files, through a NUL-prefixed virtual id whose
 *   `load` hook hands the source text to esbuild under a synthetic `.tsx` name;
 * - the specifiers with no implementation, to the harness stubs, only while the
 *   real module is absent;
 * - the modules whose importers expect exports they never declare, through a
 *   NUL-prefixed virtual id that appends those exports to the real source text.
 */
function harnessSourceResolver(): Plugin {
  return {
    name: 'harness-source-resolver',
    enforce: 'pre',

    resolveId(id, importer) {
      // Marker: already-claimed ids are returned as-is, never re-prefixed.
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
/* Filesystem guard                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Absolute path a `/@fs/` URL addresses, after query and fragment removal, one
 * round of percent-decoding, `.`/`..` normalisation and symlink resolution.
 * Returns `null` when the URL cannot be decoded.
 */
function resolveServedPath(url: string): string | null {
  let candidate: string;
  try {
    // Slicing one character before the end of the prefix keeps the leading slash.
    candidate = decodeURIComponent(
      withoutQuery(url).split('#')[0].slice(FS_URL_PREFIX.length - 1),
    );
  } catch {
    return null;
  }

  // A Windows `/@fs/` URL carries the drive letter after the leading slash.
  if (/^\/[A-Za-z]:/.test(candidate)) {
    candidate = candidate.slice(1);
  }

  const resolved = path.resolve(candidate);
  try {
    return fs.realpathSync.native(resolved).replace(/^\\\\\?\\/, '');
  } catch {
    return resolved;
  }
}

/** Whether a resolved path is one of the allowed roots or sits inside one. */
function isWithinAllowedRoot(candidate: string): boolean {
  const candidateKey = normalizeKey(candidate);
  return ALLOWED_SERVE_ROOTS.some((root) => {
    const rootKey = normalizeKey(root);
    return candidateKey === rootKey || candidateKey.startsWith(`${rootKey}/`);
  });
}

/**
 * Refuses two dev-server requests before any Vite middleware sees them:
 *
 * - `/__open-in-editor`, which spawns a local editor process;
 * - a `/@fs/` read that resolves outside `ALLOWED_SERVE_ROOTS` or onto a
 *   `DENIED_FILE_PATTERNS` name. The check runs on the decoded, normalised,
 *   symlink-resolved path, so alternate spellings of one path are refused too,
 *   and it covers every extension including `.html`.
 */
function harnessFilesystemGuard(): Plugin {
  return {
    name: 'harness-filesystem-guard',
    enforce: 'pre',

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';

        const forbid = (): void => {
          res.statusCode = 403;
          res.setHeader('Content-Type', 'text/plain');
          res.end('403 Forbidden');
        };

        if (withoutQuery(url).split('#')[0] === OPEN_IN_EDITOR_PATH) {
          forbid();
          return;
        }

        if (url.startsWith(FS_URL_PREFIX)) {
          const served = resolveServedPath(url);
          if (served === null || !isWithinAllowedRoot(served) || DENIED_PATH_EXPRESSION.test(served)) {
            forbid();
            return;
          }
        }

        next();
      });
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Configuration                                                              */
/* -------------------------------------------------------------------------- */

export default defineConfig({
  root: HARNESS,

  // No public directory: the harness serves no static assets.
  publicDir: false,

  // SPA history fallback: every client route serves the harness entry.
  appType: 'spa',

  // Both custom plugins carry `enforce: 'pre'` and run before `react()`.
  plugins: [harnessFilesystemGuard(), harnessSourceResolver(), react()],

  server: {
    host: '127.0.0.1',
    port: 4173,
    // Fail the start on a port collision; do not select another port.
    strictPort: true,
    // Only the harness page reads this server, and it is same-origin.
    cors: false,
    fs: {
      strict: true,
      // `ALLOWED_SERVE_ROOTS` is the whole set of directories the harness graph
      // reaches, Vite's own client directory included.
      allow: [...ALLOWED_SERVE_ROOTS],
      deny: [...DENIED_FILE_PATTERNS],
    },
  },

  // The default cache directory resolves against the root, which has no
  // `node_modules`.
  cacheDir: CACHE_DIR,

  // Keeps the whole dev-server log, unscrolled, so a failed start is legible in
  // whatever captures this process's output.
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
  // browser does not provide.
  //
  // A dev server does not substitute these entries into the served source: on the
  // pinned vite 4.5.14 the `vite:define` transform returns early outside a build,
  // and the client env module assigns each key onto the global object instead,
  // splitting the key on `.` and creating the missing objects as it goes. It walks
  // the keys in the order declared here, and that order is load-bearing:
  // `process.env` has to be assigned before the two keys under it, or it would
  // replace the object they were just written onto.
  //
  // Every replacement is valid JSON or a bare identifier, which is what esbuild's
  // `define` accepts, so a build substitutes the same values: `'{}'` is the JSON
  // empty object, and `REACT_APP_API_BASE_URL` resolves to the `undefined`
  // literal, which keeps the base URL that production computes today.
  define: {
    'process.env': '{}',
    'process.env.NODE_ENV': JSON.stringify('development'),
    'process.env.REACT_APP_API_BASE_URL': 'undefined',
  },
});
