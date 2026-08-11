/**
 * Vite dev-server configuration for the Playwright end-to-end harness.
 *
 * Serves the real modules under `frontend/src` through an HTML entry owned
 * entirely by `e2e/harness`. Nothing under `frontend/` or `backend/` is created,
 * modified or renamed; those files are read only for their source text.
 *
 * Configures the dev server only: it declares no `build` options.
 *
 * Host, port and origin are resolved once below and exported; `e2e/playwright.config.ts`
 * imports them from here and computes none of them itself, so the socket the harness
 * binds and the origin the runner polls are the same value by construction. This file is
 * the one that binds the socket, and `npm run harness` starts this server on its own
 * without loading `@playwright/test`.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, every choice made below.
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
 * Every module script in the document reaches it: `/@vite/client` opens with
 * `import "/@fs/<this directory>/env.mjs"`, and `/main.tsx`, `/@react-refresh` and
 * the `index.html` preamble each import `/@vite/client`.
 */
const VITE_CLIENT_DIR = path.join(HERE, 'node_modules', 'vite', 'dist', 'client');

/* -------------------------------------------------------------------------- */
/* Harness origin                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The origin the harness is served on, resolved once here and imported by
 * `e2e/playwright.config.ts`, which starts this server on it and navigates to it.
 *
 * Resolution order:
 *
 *   1. `HARNESS_PORT` - an explicit port, used verbatim.
 *   2. `E2E_PORT`     - the same thing under the name the CI job and `e2e/README.md` use.
 *   3. `CLONE_INDEX`  - an offset added to {@link BASE_PORT}, so `CLONE_INDEX=002`
 *                       resolves to 4175.
 *   4. none set        - {@link BASE_PORT}.
 *
 * A TCP port is host-global and several checkouts of this repository run concurrently on
 * one host, each with its own `CLONE_INDEX`.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, the origin-resolution decision and its risks.
 */

/** Port used when none of the three environment variables is set. */
export const BASE_PORT = 4173;

/** Lowest port accepted, above the privileged range. */
const MIN_PORT = 1024;

/** Highest port accepted. */
const MAX_PORT = 65535;

/**
 * Loopback interface the harness binds, as a literal address: `localhost` resolves to
 * either `127.0.0.1` or `::1` depending on the host's resolver order.
 */
export const HARNESS_HOST = '127.0.0.1';

/**
 * Reads a base-10 non-negative integer from the environment.
 *
 * @param name - Variable to read.
 * @returns The parsed value, or `null` when the variable is unset, empty, or not a
 *   base-10 non-negative integer. Leading zeros are accepted, so `'002'` reads as `2`.
 */
function readNonNegativeInteger(name: string): number | null {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') {
    return null;
  }

  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }

  const value = Number.parseInt(trimmed, 10);
  return Number.isSafeInteger(value) ? value : null;
}

/** Whether `candidate` is a port this file will hand out. */
function isUsablePort(candidate: number): boolean {
  return candidate >= MIN_PORT && candidate <= MAX_PORT;
}

/**
 * Resolves the port, applying the order above. An out-of-range result from either
 * variable falls through to the next step, so the harness only ever binds a port it can
 * serve on.
 */
function resolvePort(): number {
  for (const name of ['HARNESS_PORT', 'E2E_PORT']) {
    const explicitPort = readNonNegativeInteger(name);
    if (explicitPort !== null && isUsablePort(explicitPort)) {
      return explicitPort;
    }
  }

  const cloneIndex = readNonNegativeInteger('CLONE_INDEX');
  if (cloneIndex !== null && isUsablePort(BASE_PORT + cloneIndex)) {
    return BASE_PORT + cloneIndex;
  }

  return BASE_PORT;
}

/** Port the harness binds and Playwright navigates to. */
export const HARNESS_PORT = resolvePort();

/** Origin the harness is served on, the value of Playwright's `use.baseURL`. */
export const HARNESS_ORIGIN = `http://${HARNESS_HOST}:${HARNESS_PORT}`;

/* -------------------------------------------------------------------------- */
/* Module tables                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Component modules that exist on disk as extension-less FILES, not directories.
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
 * element type, and because nothing in `harness/main.tsx` is an error boundary that
 * throw unmounts the whole React root rather than only the route.
 *
 * Keys are paths under `frontend/src` without an extension. Values map an export
 * name to an expression evaluated in that module's own scope.
 *
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
 * The refusal extends to every **path** named here under every method, not only to the exact
 * method/path pairs - see {@link HARNESS_API_METHODS_BY_PATH}. The keys stay method-qualified
 * because the remedy is: only these methods are reachable from a mounted component, so only these
 * have an interception worth naming.
 *
 * Add an entry to extend. Every remedy below is spelled with a `${HARNESS_ORIGIN}`
 * prefix and no leading `**`, so a pattern claims only requests addressed to the harness
 * origin; a leading `**` would also claim a request addressed to a foreign host that
 * shares the path, and fulfilling that would hide the destination drift from the ledger
 * in `e2e/tests/harness-fixtures.ts`. A remedy copied out of this map must stay anchored,
 * here and wherever it is copied to; `e2e/tests/isolation.spec.ts` asserts that it is.
 *
 * @see docs/testing/DECISION-LOG.md - row D126, which supersedes D43, and row D213.
 */
const HARNESS_API_SURFACE: Record<string, string> = {
  // `services/api.ts` fetchTweets, reached by `components/Dashboard` through
  // `services/twitterService` getLatestTweets.
  'GET /undefined/tweets':
    'page.route(`${HARNESS_ORIGIN}/undefined/tweets*`, route => route.fulfill({ json: [] }))',

  // `harness/stubs/analyticsService.ts` getTrendData. `e2e/fixtures/trends.json`
  // is the payload a spec fulfils with.
  'GET /api/trends':
    'page.route(`${HARNESS_ORIGIN}/api/trends*`, route => route.fulfill({ path: "fixtures/trends.json" }))',

  // `harness/stubs/configService.ts` updateTwitterAPIConfig, from the
  // `components/Configuration` submit handler.
  'POST /api/config/twitter':
    'page.route(`${HARNESS_ORIGIN}/api/config/twitter`, route => route.fulfill({ json: {} }))',
};

/**
 * Every pathname {@link HARNESS_API_SURFACE} declares, mapped to the methods it declares for it.
 *
 * Derived from that map's own keys, so the two cannot drift: adding an entry there adds its path
 * here. It is what makes the fail-closed responder **path**-scoped while the remedies stay
 * method-specific - a request to a declared path is refused whichever method it carries, and the
 * remedy names either the interception for that exact method/path pair or, for a method the path
 * does not declare, the methods it does.
 *
 * Path-scoped is the correct granularity because the property being protected is "no flow is
 * satisfied by a server default". A method-scoped refusal left a declared path answerable by the
 * SPA fallback: `GET /api/config/twitter` was answered `200 text/html` with the harness document,
 * which a `fetch` reports as `response.ok`, and `HEAD` on all three paths likewise. The browser-side
 * ledger in `e2e/tests/harness-fixtures.ts` has always been path-scoped, so the two layers
 * disagreed - it recorded such a request as un-intercepted while the server had already answered it
 * successfully.
 *
 * @see docs/testing/DECISION-LOG.md - row D410, which refines D126.
 */
const HARNESS_API_METHODS_BY_PATH: ReadonlyMap<string, readonly string[]> = (() => {
  const byPath = new Map<string, string[]>();

  for (const key of Object.keys(HARNESS_API_SURFACE)) {
    const separator = key.indexOf(' ');
    const method = key.slice(0, separator);
    const pathname = key.slice(separator + 1);
    const declared = byPath.get(pathname);

    if (declared === undefined) {
      byPath.set(pathname, [method]);
    } else if (!declared.includes(method)) {
      declared.push(method);
    }
  }

  return byPath;
})();

/** Status the harness answers an un-intercepted {@link HARNESS_API_SURFACE} request with. */
const API_NOT_INTERCEPTED_STATUS = 503;

/** `error` of every un-intercepted-request body, and the dev-server log prefix. */
const API_NOT_INTERCEPTED_ERROR = 'harness-api-not-intercepted';

/**
 * Icon path a browser requests on its own on a top-level navigation, answered
 * `204 No Content` with no body.
 *
 * The harness ships no icon and `e2e/harness/index.html` declares none, so no document
 * references this path. Matched exactly, as the paths of {@link HARNESS_API_METHODS_BY_PATH} are:
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

/**
 * Dev-server endpoint that spawns a local editor process; the harness never uses it.
 *
 * Matched as a **path prefix, case-insensitively**, by {@link isOpenInEditorPath} rather than by
 * equality, because that is how the endpoint is reachable. Vite mounts it with
 * `middlewares.use('/__open-in-editor', launchEditorMiddleware())`, and connect's route matching
 * lower-cases both sides and accepts the route followed by `/`, by a sub-path or by a query string.
 * `/__open-in-editor/?file=x`, `/__open-in-editor/anything?file=x` and `/__OPEN-IN-EDITOR?file=x`
 * therefore all reach the middleware while failing an equality test against the string below.
 *
 * @see docs/testing/DECISION-LOG.md - row D317.
 */
const OPEN_IN_EDITOR_PATH = '/__open-in-editor';

/**
 * Prefix of every dev-server control endpoint. No module, document or asset in the harness graph is
 * addressed under it, so it is the one prefix that can be refused wholesale.
 *
 * Used by {@link isDevServerControlPath} for the paths that carry no legitimate traffic, and mirrored
 * in `e2e/tests/harness-fixtures.ts`, which aborts them in the browser before they leave.
 */
const CONTROL_PATH_PREFIX = '/__';

/** Placeholder Vite substitutes for the leading NUL of a virtual id in a URL. */
const NULL_BYTE_URL_PLACEHOLDER = '__x00__';

/**
 * URL prefix of every request Vite addresses to a module rather than to a path: `/@fs/`,
 * `/@id/`, `/@vite/` and `/@react-refresh`. A client route never begins with it, so it is the
 * one prefix {@link isClientRoutePath} can refuse wholesale.
 */
const MODULE_URL_PREFIX = '/@';

/**
 * `Accept` value {@link harnessRouteAcceptNormaliser} substitutes when a client-route request
 * carries one the SPA fallback would refuse. The single media type the fallback tests for, and
 * exactly what the document it serves is.
 */
const ROUTE_ACCEPT = 'text/html';


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
 * The `/@fs/` prefix and, on Windows, the drive letter are stripped before the check: a
 * `/@fs/C:/...` URL carries one legitimate colon. `LEADING_DRIVE_EXPRESSION` matches only the
 * stripped path, which is what keeps every `/@fs/` request on Windows servable - React,
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

/**
 * Whether a request path addresses the open-in-editor endpoint in any spelling connect accepts.
 *
 * Compared lower-cased, and as a prefix that may be followed by nothing, by `/` or by a sub-path -
 * which is exactly what `connect`'s `use(route, handler)` matching admits. Applied to the raw path and
 * to the fully decoded one, so neither a percent-encoded separator nor a mixed-case spelling gets past
 * it.
 *
 * @param pathname - Request path with query and fragment already removed.
 */
function isOpenInEditorPath(pathname: string): boolean {
  const candidate = pathname.toLowerCase();
  if (candidate === OPEN_IN_EDITOR_PATH) {
    return true;
  }
  return candidate.startsWith(`${OPEN_IN_EDITOR_PATH}/`) || candidate.startsWith(`${OPEN_IN_EDITOR_PATH}?`);
}

/**
 * Whether a request path addresses a dev-server control endpoint rather than the harness graph.
 *
 * Every Vite control endpoint - the editor launcher, the inspector, the liveness ping - is mounted
 * under {@link CONTROL_PATH_PREFIX}, and nothing the harness serves is. Refusing the prefix means a
 * future Vite version that adds another such endpoint is closed by default rather than on discovery.
 *
 * @param pathname - Request path with query and fragment already removed.
 */
function isDevServerControlPath(pathname: string): boolean {
  return pathname.toLowerCase().startsWith(CONTROL_PATH_PREFIX);
}

/**
 * Whether a `/@id/` request names a virtual module this configuration registered.
 *
 * The `/@id/` prefix is how Vite serves a module id that is not a path, and the harness has exactly
 * four of them - the extension-less component files - plus the compatibility wrappers, all registered
 * in {@link virtualModules} at config time. Anything else under that prefix is not a harness module,
 * so it is refused here rather than handed to the plugin container: an unregistered id falls through to
 * Vite's own transform pipeline, which resolves what is left as a filesystem path.
 *
 * Both the raw and the fully decoded spelling are accepted, because Vite applies `decodeURI` to the
 * request before it unwraps the id, and both are checked against the same exact registry - so a
 * spelling that decodes to anything other than a registered id is refused either way.
 *
 * @param pathname - Request path with query and fragment already removed.
 * @param decoded - The same path, fully percent-decoded.
 */
function isRegisteredVirtualModulePath(pathname: string, decoded: string): boolean {
  const unwrap = (candidate: string): string => {
    const withoutPrefix = candidate.slice(VIRTUAL_ID_URL_PREFIX.length);
    return withoutPrefix.startsWith(NULL_BYTE_URL_PLACEHOLDER)
      ? `\0${withoutPrefix.slice(NULL_BYTE_URL_PLACEHOLDER.length)}`
      : withoutPrefix;
  };

  return [pathname, decoded].some((candidate) =>
    candidate.startsWith(VIRTUAL_ID_URL_PREFIX)
      ? virtualModules.has(normalizeKey(withoutQuery(unwrap(candidate))))
      : false,
  );
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
 * Refuses five classes of dev-server request before any Vite middleware sees them:
 *
 * - every spelling of `/__open-in-editor`, which spawns a local editor process, and then the whole
 *   `/__` control prefix behind it - see {@link isOpenInEditorPath} and
 *   {@link isDevServerControlPath};
 * - a `/@id/` virtual-module request naming an id this configuration did not register - see
 *   {@link isRegisteredVirtualModulePath};
 * - any request path, `/@fs/` or root-relative, that uses NTFS alternate-data-stream syntax or a
 *   Windows 8.3 short name - see {@link usesAlternateWindowsSpelling};
 * - a **root-relative** read that resolves outside `ALLOWED_SERVE_ROOTS` or onto a
 *   `DENIED_FILE_PATTERNS` name;
 * - a `/@fs/` read that resolves outside `ALLOWED_SERVE_ROOTS` or onto a `DENIED_FILE_PATTERNS`
 *   name. The check runs on the decoded, normalised, symlink-resolved path and covers every
 *   extension, `.html` included.
 *
 * Containment applies to **both** path branches. It used to apply only to `/@fs/`, which left the
 * root-relative branch judging names alone: `resolveRootRelativePath` keeps `..` segments, so an
 * encoded traversal resolved outside the harness root and matched no denied name.
 *
 * Every check runs on the fully percent-decoded path *and* on the raw URL, so neither a nested
 * encoding nor an encoding Vite would not decode can carry a colon, a tilde or a traversal past it.
 *
 * `e2e/tests/isolation.spec.ts` drives each class through `request.fetch`, which bypasses every
 * `page.route`, so what it asserts is this middleware rather than a browser-side rule.
 *
 * @see docs/testing/DECISION-LOG.md - rows D110, D115 and D317.
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

        // Refused in every spelling connect would route to the editor launcher, and then the whole
        // control prefix behind it, on the raw path and on the decoded one.
        if (
          isOpenInEditorPath(pathOnly) ||
          isOpenInEditorPath(decoded) ||
          isDevServerControlPath(pathOnly) ||
          isDevServerControlPath(decoded)
        ) {
          forbid();
          return;
        }

        // A virtual module id is not a path, so the path checks below do not apply to it - but only a
        // *registered* id is exempt from them. See isRegisteredVirtualModulePath.
        if (
          pathOnly.startsWith(VIRTUAL_ID_URL_PREFIX) ||
          decoded.startsWith(VIRTUAL_ID_URL_PREFIX)
        ) {
          if (isRegisteredVirtualModulePath(pathOnly, decoded)) {
            next();
          } else {
            forbid();
          }
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
          // `isWithinAllowedRoot` on this branch too, not only on the `/@fs/` one:
          // `resolveRootRelativePath` preserves `..` segments, so `/%2e%2e/%2e%2e/frontend/package.json`
          // resolves outside `e2e/harness` while matching no denied *name*. Containment is the check
          // that refuses it; the deny list only ever covered sensitive names inside a root.
          if (
            served === null ||
            !isWithinAllowedRoot(served) ||
            DENIED_PATH_EXPRESSION.test(served)
          ) {
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
 * Remedy named for a request to a declared API path under a method that path does not declare.
 *
 * Such a request is not a flow this harness can satisfy - no mounted component issues it - so the
 * remedy states that first and then gives both ways forward: correct the request, or declare the
 * pair and intercept it. The `page.route` call is spelled with a literal `${HARNESS_ORIGIN}`, as
 * every entry of {@link HARNESS_API_SURFACE} is, so a remedy copied out of an error message stays
 * anchored to the harness origin rather than claiming the path on any host.
 *
 * @param method - Method the request carried.
 * @param pathname - Declared API path it addressed.
 * @param declared - Methods {@link HARNESS_API_SURFACE} declares for that path.
 */
function undeclaredMethodRemedy(
  method: string,
  pathname: string,
  declared: readonly string[],
): string {
  return (
    `no mounted component issues ${method} ${pathname}: this path is declared for ` +
    `${declared.join(', ')} only. Either correct the request, or add "${method} ${pathname}" to ` +
    'HARNESS_API_SURFACE and intercept it with ' +
    'page.route(`${HARNESS_ORIGIN}' +
    `${pathname}\`, route => route.fulfill({ json: {} }))`
  );
}

/**
 * Answers every request to a {@link HARNESS_API_METHODS_BY_PATH} path that reached this server with
 * {@link API_NOT_INTERCEPTED_STATUS}, answers {@link FAVICON_PATH} with
 * {@link FAVICON_STATUS}, and passes every other request through.
 *
 * A request reaches here only when no `page.route` claimed it, so reaching here *is*
 * the missing interception. The response names the request and the interception the
 * spec is missing, and the same line is written to the dev-server log, which
 * `e2e/playwright.config.ts` pipes into the run output.
 *
 * The refusal is keyed by **path** and the remedy by method: a declared path is refused whichever
 * method it carries, so no method can be answered by a server default, while the remedy is the
 * exact `page.route` snippet for a declared method/path pair and
 * {@link undeclaredMethodRemedy} otherwise. Measured before that widening: `GET
 * /api/config/twitter` was answered `200 text/html` with the harness document - `response.ok`, and
 * a credential-write endpoint at that - and `HEAD` on all three declared paths answered `200` too.
 *
 * Runs ahead of Vite's own middleware, so these paths never reach the SPA fallback:
 * `connect-history-api-fallback` answers `index.html` to a `fetch`, whose `Accept`
 * header is a bare wildcard, and `response.ok` is then true for an HTML body.
 *
 * `Cache-Control: no-store`, so a reload re-issues the request and a spec sees it.
 *
 * @see docs/testing/DECISION-LOG.md - row D126, refined by row D410.
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

        const declaredMethods = HARNESS_API_METHODS_BY_PATH.get(pathname);
        if (declaredMethods === undefined) {
          next();
          return;
        }

        const declaredRemedy: string | undefined = HARNESS_API_SURFACE[`${method} ${pathname}`];
        const remedy =
          declaredRemedy ?? undeclaredMethodRemedy(method, pathname, declaredMethods);

        const request = `${method} ${req.url ?? pathname}`;

        /*
         * "install <snippet>" for a declared method/path pair, whose remedy *is* the call to
         * install; the undeclared-method remedy is a sentence of its own and is logged as written.
         */
        const guidance = declaredRemedy === undefined ? remedy : `install ${remedy}`;

        server.config.logger.warn(
          `[${API_NOT_INTERCEPTED_ERROR}] ${request} was answered ` +
            `${API_NOT_INTERCEPTED_STATUS}; ${guidance}`,
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
/* Client-route Accept normaliser                                             */
/* -------------------------------------------------------------------------- */

/**
 * Whether the SPA history fallback would refuse a request carrying `accept`.
 *
 * These are the three header conditions `connect-history-api-fallback` - the package
 * `appType: 'spa'` runs the fallback through - tests before it rewrites, restated so the
 * decision to normalise is made against the same rule that would otherwise refuse:
 * the header must be present, must not lead with `application/json`, and must name
 * either `text/html` or a bare wildcard somewhere.
 *
 * @param accept - The request's `Accept` header, absent as `undefined`.
 * @returns `true` when the fallback would pass the request on rather than rewrite it.
 */
function fallbackRefusesAccept(accept: string | undefined): boolean {
  if (typeof accept !== 'string') {
    return true;
  }
  if (accept.indexOf('application/json') === 0) {
    return true;
  }
  return !(accept.includes(ROUTE_ACCEPT) || accept.includes('*/*'));
}

/**
 * Whether `pathname` addresses a client route of `harness/main.tsx` rather than a module, an
 * asset, a control endpoint or an API path.
 *
 * Four exclusions, narrowest first. A module URL is refused by prefix. A control endpoint is
 * refused by prefix. Every path {@link HARNESS_API_METHODS_BY_PATH} declares is refused by exact
 * match **whatever method the request carries**, so an API path is never mistaken for a route even
 * though none of them carries an extension - and cannot be promoted into one by the method it was
 * asked with. What remains is refused unless its last segment is extension-less, which is what
 * separates `/tweets` from `/main.tsx`, `/index.html` and every asset request.
 *
 * The API exclusion is belt and braces: {@link harnessApiFailClosed} is registered ahead of the
 * normaliser and answers those paths itself, so nothing reaches here to be promoted. It is stated
 * anyway, so that reordering the two plugins could not quietly turn a declared API path back into
 * a client route.
 *
 * @param pathname - Request path with query and fragment removed.
 *
 * @see docs/testing/DECISION-LOG.md - rows D378 and D410.
 */
function isClientRoutePath(pathname: string): boolean {
  if (pathname.startsWith(MODULE_URL_PREFIX) || pathname.startsWith(CONTROL_PATH_PREFIX)) {
    return false;
  }
  if (pathname === FAVICON_PATH) {
    return false;
  }
  if (HARNESS_API_METHODS_BY_PATH.has(pathname)) {
    return false;
  }
  return path.posix.extname(pathname) === '';
}

/**
 * Substitutes {@link ROUTE_ACCEPT} on a client-route request whose own `Accept` would make the
 * SPA history fallback pass it through to a 404, and passes every other request on untouched.
 *
 * `appType: 'spa'` answers a client route by rewriting it to the harness entry, but only for a
 * request whose `Accept` satisfies {@link fallbackRefusesAccept}. A browser navigation always
 * does; a client that asks for JSON, asks for a script, or sends no `Accept` at all does not, and
 * received 404 for `/tweets` while a navigation to the same path received the harness page. The
 * route table is a property of the harness, not of the requesting client, so the answer is made
 * the same for all of them.
 *
 * Ordered after {@link harnessFilesystemGuard} and {@link harnessApiFailClosed} so a refused
 * path is never reconsidered here. This middleware only ever rewrites one request header and
 * always calls `next()`: it serves nothing, so it can neither answer a path those guards
 * refused nor turn a refusal into a success. A path that reaches the fallback is answered with
 * the harness entry, which is already served at `/` - no request reaches a file it could not
 * reach before.
 *
 * @see docs/testing/DECISION-LOG.md - row D378.
 */
function harnessRouteAcceptNormaliser(): Plugin {
  return {
    name: 'harness-route-accept-normaliser',
    enforce: 'pre',

    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const method = req.method ?? '';

        // The fallback rewrites these two methods only; normalising any other would
        // promise an answer it still would not give.
        if (method !== 'GET' && method !== 'HEAD') {
          next();
          return;
        }

        const pathname = withoutQuery(req.url ?? '').split('#')[0];
        if (!isClientRoutePath(pathname) || !fallbackRefusesAccept(req.headers.accept)) {
          next();
          return;
        }

        req.headers.accept = ROUTE_ACCEPT;
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

  // All four custom plugins carry `enforce: 'pre'` and run before `react()`. The
  // filesystem guard is first, so a refused request is never answered by a later
  // plugin; the Accept normaliser follows both guards, so it never reconsiders a path
  // either of them refused.
  plugins: [
    harnessFilesystemGuard(),
    harnessApiFailClosed(),
    harnessRouteAcceptNormaliser(),
    harnessSourceResolver(),
    react(),
  ],

  server: {
    // Host and port are the values resolved in the harness-origin section above,
    // which `e2e/playwright.config.ts` imports from this file, so the server and the
    // runner cannot disagree. The port is clone-specific: see that section.
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
  // object in the order below, and `process.env` must come first so it does not replace the
  // object the two keys under it are written onto.
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
