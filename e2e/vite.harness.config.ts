/**
 * Vite dev-server configuration for the Playwright end-to-end harness.
 *
 * Serves the real modules under `frontend/src` through an HTML entry owned
 * entirely by `e2e/harness`. Nothing under `frontend/` or `backend/` is created,
 * modified or renamed; those files are read only for their source text.
 *
 * Configures the dev server only: it declares no `build` options.
 *
 * Host and port come from `./harness-origin`, which `e2e/playwright.config.ts`
 * imports as well. This file resolves neither itself, so the socket the harness
 * binds and the origin the runner polls are the same value by construction.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, every choice made below.
 */

import fs from 'node:fs';
import path from 'node:path';
import { defineConfig, transformWithEsbuild, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

import { HARNESS_HOST, HARNESS_PORT } from './harness-origin';

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
 * Every module script in the document reaches it: `/@vite/client` opens with
 * `import "/@fs/<this directory>/env.mjs"`, and `/main.tsx`, `/@react-refresh` and
 * the `index.html` preamble each import `/@vite/client`.
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
 * Named exports the frontend imports but never declares, supplied so the importing
 * module can load at all. Each entry is appended to the end of the real module's
 * source text; nothing in that text is rewritten.
 *
 * Every value is `undefined`, which is what the same import already carries under
 * Jest and CommonJS, so the importer reaches the same branch here as everywhere
 * else. `TweetCard` in particular stays `undefined`: rendering it is an invalid
 * element type that unmounts the route.
 *
 * Keys are paths under `frontend/src` without an extension. Values map an export
 * name to an expression evaluated in that module's own scope.
 *
 * Add an entry to extend.
 *
 * @see docs/testing/DECISION-LOG.md - row D42.
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
 * The only directories this dev server may read over `/@fs/`, and the whole of the
 * harness graph: the harness itself, which contains `harness/stubs`; the pre-bundle
 * cache; the Vite client runtime; and the frontend sources and package tree the
 * aliases resolve to.
 *
 * Both `server.fs.allow` and `harnessFilesystemGuard` below read this list, the
 * guard through `isWithinAllowedRoot`.
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

/**
 * NTFS alternate-data-stream syntax in a request path, such as `secret.env::$DATA`.
 *
 * Invariant: a colon is refused anywhere except immediately after a single leading drive letter,
 * which is the one legitimate colon a `/@fs/C:/...` URL contains. No path in the harness graph
 * carries any other colon.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110 and D115.
 */
const NTFS_STREAM_EXPRESSION = /:/;

/** Leading `/<drive letter>:` of a `/@fs/` URL on Windows, the one legitimate colon. */
const LEADING_DRIVE_EXPRESSION = /^\/[A-Za-z]:/;

/**
 * Windows 8.3 short-name syntax, such as `PROGRA~1` or `SECRET~1.ENV`.
 *
 * Invariant: `~<digit>` is refused anywhere. No path in the harness graph contains a tilde.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110 and D115.
 */
const SHORT_NAME_EXPRESSION = /~\d/;

/** Bound on repeated percent-decoding, so a nested encoding cannot outrun the check. */
const MAX_DECODE_PASSES = 4;
/* -------------------------------------------------------------------------- */
/* Harness API surface                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Every API request the four mounted components issue, and the interception a spec
 * must install to drive it.
 *
 * Keyed `<METHOD> <pathname>` and matched exactly. None of these keys is a client
 * route: `frontend/src/services/api.ts` interpolates an undefined base URL, so its
 * requests all begin `/undefined/`, and the two stubs under `harness/stubs` request
 * paths under `/api/`. The client routes `/`, `/tweets`, `/analytics` and
 * `/configuration` are untouched and keep the SPA fallback.
 *
 * Contract: the dev server answers every entry here with
 * {@link API_NOT_INTERCEPTED_STATUS} and never with a success status, so no flow can
 * be satisfied by a server default and every payload a spec asserts on is a payload
 * that spec supplied. `page.route` intercepts in the browser, before the request is
 * issued, so an installed interception is answered without reaching this server at
 * all.
 *
 * Add an entry to extend.
 *
 * @see docs/testing/DECISION-LOG.md - row D126, which supersedes D43.
 */
const HARNESS_API_SURFACE: Record<string, string> = {
  // `services/api.ts` fetchTweets, reached by `components/Dashboard` through
  // `services/twitterService` getLatestTweets.
  'GET /undefined/tweets':
    "page.route('**/undefined/tweets*', route => route.fulfill({ json: [] }))",

  // `harness/stubs/analyticsService.ts` getTrendData. `e2e/fixtures/trends.json`
  // is the payload a spec fulfils with.
  'GET /api/trends':
    "page.route('**/api/trends*', route => route.fulfill({ path: 'fixtures/trends.json' }))",

  // `harness/stubs/configService.ts` updateTwitterAPIConfig, from the
  // `components/Configuration` submit handler.
  'POST /api/config/twitter':
    "page.route('**/api/config/twitter', route => route.fulfill({ json: {} }))",
};

/** Status the harness answers an un-intercepted {@link HARNESS_API_SURFACE} request with. */
const API_NOT_INTERCEPTED_STATUS = 503;

/** `error` of every un-intercepted-request body, and the dev-server log prefix. */
const API_NOT_INTERCEPTED_ERROR = 'harness-api-not-intercepted';

/**
 * Icon path a browser requests on its own on a top-level navigation, answered
 * `204 No Content` with no body.
 *
 * The harness ships no icon and `e2e/harness/index.html` declares none, so no document
 * references this path. Matched exactly, as the keys of {@link HARNESS_API_SURFACE} are:
 * any other unknown dotted path still 404s.
 *
 * @see docs/testing/DECISION-LOG.md - row D147.
 */
const FAVICON_PATH = '/favicon.ico';

/** Status {@link FAVICON_PATH} is answered with. */
const FAVICON_STATUS = 204;

/** URL prefix under which Vite serves a file by absolute path. */
const FS_URL_PREFIX = '/@fs/';

/**
 * URL prefix under which Vite serves a *virtual* module id, with the leading NUL encoded as
 * `__x00__`.
 *
 * Exempt from the alternate-spelling and denied-path checks: a harness virtual id embeds an
 * absolute path and so carries two colons, and a `/@id/` request never becomes a filesystem read
 * by path - it goes to the plugin container, where `harnessSourceResolver.resolveId` returns a
 * NUL-prefixed id only for a key of `virtualModules`, the map built once at config time below.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110 and D115.
 */
const VIRTUAL_ID_URL_PREFIX = '/@id/';

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
  let candidate = fullyDecode(withoutQuery(url).split('#')[0]);
  if (candidate === null) {
    return null;
  }
  candidate = candidate.slice(FS_URL_PREFIX.length - 1);

  // A Windows `/@fs/` URL carries the drive letter after the leading slash.
  if (LEADING_DRIVE_EXPRESSION.test(candidate)) {
    candidate = candidate.slice(1);
  }

  const resolved = path.resolve(candidate);
  try {
    return fs.realpathSync.native(resolved).replace(/^\\\\\?\\/, '');
  } catch {
    return resolved;
  }
}

/**
 * Percent-decodes until the result stops changing, so `%252e` cannot hide a `.` from the checks
 * below by surviving a single pass. Returns `null` when the input is not decodable.
 *
 * @param value - Raw request path, query and fragment already removed.
 */
function fullyDecode(value: string): string | null {
  let current = value;
  for (let pass = 0; pass < MAX_DECODE_PASSES; pass += 1) {
    let next: string;
    try {
      next = decodeURIComponent(current);
    } catch {
      return null;
    }
    if (next === current) {
      return current;
    }
    current = next;
  }
  return current;
}

/**
 * Path a root-relative request addresses, resolved against the Vite root.
 *
 * `/@fs/` URLs are handled by {@link resolveServedPath}; everything else Vite serves is resolved
 * against `root`, which is `e2e/harness`. Returns `null` when the URL cannot be decoded.
 *
 * @param url - Raw request URL as the middleware receives it.
 */
function resolveRootRelativePath(url: string): string | null {
  const decoded = fullyDecode(withoutQuery(url).split('#')[0]);
  if (decoded === null) {
    return null;
  }
  return path.resolve(HARNESS, `.${decoded.startsWith('/') ? decoded : `/${decoded}`}`);
}

/**
 * Whether a request path uses an alternate Windows spelling of a filename.
 *
 * Applied to every request, `/@fs/` or not, before the path is resolved: `path.resolve` and
 * `fs.realpathSync` both preserve an ADS suffix, and a short name resolves to the long name only
 * after the deny check would already have passed.
 *
 * The `/@fs/` prefix and, on Windows, the drive letter are stripped before the check, because a
 * `/@fs/C:/...` URL carries one legitimate colon. Testing `LEADING_DRIVE_EXPRESSION` against the
 * unstripped path can never match, which would refuse every `/@fs/` request on Windows - React,
 * ReactDOM, the store slices and Vite's own dev client included.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110 and D115.
 *
 * @param pathname - Request path, query and fragment removed; decoded or raw.
 * @param isFsRequest - `true` when the path begins with {@link FS_URL_PREFIX}.
 */
function usesAlternateWindowsSpelling(pathname: string, isFsRequest: boolean): boolean {
  let candidate = pathname;

  if (isFsRequest && candidate.startsWith(FS_URL_PREFIX)) {
    // Slicing one character before the end of the prefix keeps the leading slash.
    candidate = candidate.slice(FS_URL_PREFIX.length - 1);

    // Only a `/@fs/` path may carry a drive letter; a root-relative one has no business with a colon.
    if (LEADING_DRIVE_EXPRESSION.test(candidate)) {
      candidate = candidate.slice(3);
    }
  }

  return NTFS_STREAM_EXPRESSION.test(candidate) || SHORT_NAME_EXPRESSION.test(candidate);
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
 * Refuses four classes of dev-server request before any Vite middleware sees them:
 *
 * - `/__open-in-editor`, which spawns a local editor process;
 * - any request path, `/@fs/` or root-relative, that uses NTFS alternate-data-stream syntax or a
 *   Windows 8.3 short name - see {@link usesAlternateWindowsSpelling};
 * - a **root-relative** read that resolves onto a `DENIED_FILE_PATTERNS` name;
 * - a `/@fs/` read that resolves outside `ALLOWED_SERVE_ROOTS` or onto a `DENIED_FILE_PATTERNS`
 *   name. The check runs on the decoded, normalised, symlink-resolved path and covers every
 *   extension, `.html` included.
 *
 * Every check runs on the fully percent-decoded path *and* on the raw URL, so neither a nested
 * encoding nor an encoding Vite would not decode can carry a colon or a tilde past it.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110 and D115.
 */
function harnessFilesystemGuard(): Plugin {
  return {
    name: 'harness-filesystem-guard',
    enforce: 'pre',

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        const pathOnly = withoutQuery(url).split('#')[0];
        const decoded = fullyDecode(pathOnly);

        const forbid = (): void => {
          res.statusCode = 403;
          res.setHeader('Content-Type', 'text/plain');
          res.end('403 Forbidden');
        };

        if (decoded === null) {
          forbid();
          return;
        }

        if (pathOnly === OPEN_IN_EDITOR_PATH) {
          forbid();
          return;
        }

        // A virtual module id is not a path; see VIRTUAL_ID_URL_PREFIX.
        if (pathOnly.startsWith(VIRTUAL_ID_URL_PREFIX)) {
          next();
          return;
        }

        const isFsRequest = url.startsWith(FS_URL_PREFIX);

        // Checked on both the decoded path and the raw one: the raw form is what Vite itself sees.
        if (
          usesAlternateWindowsSpelling(decoded, isFsRequest) ||
          usesAlternateWindowsSpelling(pathOnly, isFsRequest)
        ) {
          forbid();
          return;
        }

        if (isFsRequest) {
          const served = resolveServedPath(url);
          if (served === null || !isWithinAllowedRoot(served) || DENIED_PATH_EXPRESSION.test(served)) {
            forbid();
            return;
          }
        } else {
          const served = resolveRootRelativePath(url);
          if (served === null || DENIED_PATH_EXPRESSION.test(served)) {
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
/* API fail-closed guard                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Answers every {@link HARNESS_API_SURFACE} request that reached this server with
 * {@link API_NOT_INTERCEPTED_STATUS}, answers {@link FAVICON_PATH} with
 * {@link FAVICON_STATUS}, and passes every other request through.
 *
 * A request reaches here only when no `page.route` claimed it, so reaching here *is*
 * the missing interception. The response names the request and the interception the
 * spec is missing, and the same line is written to the dev-server log, which
 * `e2e/playwright.config.ts` pipes into the run output.
 *
 * Runs ahead of Vite's own middleware, so these paths never reach the SPA fallback -
 * `connect-history-api-fallback` answers `index.html` to a `fetch`, whose `Accept`
 * header is a bare wildcard, which would make `response.ok` true for an HTML body.
 *
 * `Cache-Control: no-store`, so a reload re-issues the request and a spec sees it.
 */
function harnessApiFailClosed(): Plugin {
  return {
    name: 'harness-api-fail-closed',
    enforce: 'pre',

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const method = req.method ?? '';
        const pathname = withoutQuery(req.url ?? '').split('#')[0];

        // Browser-initiated icon probe; the harness ships no icon, so it carries no body.
        if (pathname === FAVICON_PATH) {
          res.statusCode = FAVICON_STATUS;
          res.end();
          return;
        }

        const remedy = HARNESS_API_SURFACE[`${method} ${pathname}`];
        if (remedy === undefined) {
          next();
          return;
        }

        const request = `${method} ${req.url ?? pathname}`;
        server.config.logger.warn(
          `[${API_NOT_INTERCEPTED_ERROR}] ${request} was answered ` +
            `${API_NOT_INTERCEPTED_STATUS}; install ${remedy}`,
        );

        res.statusCode = API_NOT_INTERCEPTED_STATUS;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.setHeader('Cache-Control', 'no-store');
        res.end(
          JSON.stringify({
            error: API_NOT_INTERCEPTED_ERROR,
            request,
            remedy,
          }),
        );
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

  // All three custom plugins carry `enforce: 'pre'` and run before `react()`. The
  // filesystem guard is first, so a refused request is never answered by a later
  // plugin.
  plugins: [harnessFilesystemGuard(), harnessApiFailClosed(), harnessSourceResolver(), react()],

  server: {
    // Host and port come from `./harness-origin`, which `e2e/playwright.config.ts`
    // reads as well, so the server and the runner cannot disagree. The port is
    // clone-specific: see that module for how it is resolved.
    host: HARNESS_HOST,
    port: HARNESS_PORT,
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

  // `frontend/src/services/api.ts` reads `process.env` at module scope, which a browser does
  // not provide.
  //
  // Declaration order is load-bearing: the dev client assigns these keys onto the global
  // object in the order below, so `process.env` must come first or it would replace the object
  // the two keys under it were just written onto.
  //
  // `REACT_APP_API_BASE_URL` resolves to the `undefined` literal, which keeps the base URL
  // production computes today - hence the `/undefined/tweets` key in `HARNESS_API_SURFACE`.
  //
  // @see docs/testing/DECISION-LOG.md - section 4.
  define: {
    'process.env': '{}',
    'process.env.NODE_ENV': JSON.stringify('development'),
    'process.env.REACT_APP_API_BASE_URL': 'undefined',
  },
});
