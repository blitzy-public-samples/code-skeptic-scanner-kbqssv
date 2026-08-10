# Current-state security gap register

**What this document is.** Every security exposure found in this repository that is **still present**, with
the reason it was not fixed and what a human has to do about it. It exists because a decline that lives only
in a review reply is, six months later, indistinguishable from a finding nobody noticed.

**What it is not.** It is not a defect list — `DECISION-LOG.md` §23 is the noted-but-not-fixed register, and
it catalogues defects observed while testing, organised by discovery. This document is organised by exposure
and is only about security. It is also not a record of what was fixed: the exposures that were closed are in
`DECISION-LOG.md` §34, and none of them appears here.

**Why anything is declined at all.** This delivery is a **test** deliverable. Its authorized write surface is
frozen by the Agent Action Plan, which permits exactly two production touches — converting `app/api/routes`
into a package and declaring four `Settings` fields — and §0.8.2 excludes the rest of the production tree,
`infrastructure/**`, `scripts/**`, `documentation/**` and `.github/workflows/cd.yml` by name. Fixing an
application vulnerability here would mean an unauthorized change to code this programme exists to *test*.
Every row below therefore cites the clause that puts it out of reach, and no row is declined on the grounds
that it is hard, small or unlikely. Group 5 is the one exception to the *reason*: its subject is inside the
write surface, and what fixes it there is a user-specified rule rather than an AAP exclusion.

Each row states the exposure as a fact about the code as delivered, so it can be read without the review that
raised it.

---

## 1. Application code — unauthenticated, unvalidated business operations

The AAP clause: **§0.8.2**, "Source code modifications. Every backend and frontend production module other
than the two pre-authorized touches", which then names several of these specifically — "No login route, no
token endpoint, no RBAC, no `verify_token` implementation" and "No fix to the SQLAlchemy-against-Firestore
mismatch in the routes module."

Row ids here are **append-only**. Rows 26 to 28 were added when a runtime QA pass drove the credential screen
in a real browser and measured three exposures this register had not stated; they sit at the end of this group
rather than beside row 9, because a reader citing "row 9" or "row 14" must find the same row later
(`DECISION-LOG.md` D401).

| # | Exposure as it exists in the code | Attacker value | What a human must do |
|---|-----------------------------------|----------------|----------------------|
| 1 | `app/api/routes/tweets.py` implements `GET /tweets`, `GET /tweets/{id}` and `POST /tweets/{id}/responses` with no authentication and no authorization of any kind. `app/api/dependencies.py` defines `get_current_user`, but no route depends on it, and the `verify_token` it imports does not exist anywhere. | Anyone who can reach the service reads every tweet and writes a response to any of them. There is no identity to attribute the write to. | Implement a token verifier, attach a dependency to all three operations, and rate-limit the write. This is product work: the routers for `users`, `analytics` and `config` are deliberately empty shells, so the authorization model has to be designed rather than restored. |
| 2 | `app/services/analytics_service.py` builds both queries by f-string interpolation of caller-supplied date strings straight into BigQuery SQL, with no validation. An inverted or malformed range is accepted verbatim. | A value such as `2024-01-01' OR 1=1 --` changes the predicate. Whether it reaches a caller depends on the absent HTTP surface above, so today the exposure is latent rather than reachable — which will change the moment an analytics route is added. | Use named BigQuery parameters and validate the range as dates rather than strings. The suite already asserts the current interpolation as a fact, including the emitted `BETWEEN` clause, so the tests will show precisely what changes. |
| 3 | `app/core/security.py` computes expiry as `expires_delta or timedelta(minutes=15)`, so a caller passing `timedelta(0)` silently receives fifteen minutes, and `ACCESS_TOKEN_EXPIRE_MINUTES = 30` is ignored entirely. There is no verifier, no claim validation, no revocation and no session policy. | A token cannot be revoked and its lifetime is not the configured one. Nothing consumes these tokens today, because no route authenticates. | Test the delta against `None` rather than for truthiness, honour the configured expiry, and implement verification and a revocation path alongside the authorization work in row 1. The suite pins the current behaviour with a frozen clock at `exp == 1704068100`, so a fix will fail that assertion by design — update it to the new contract. |
| 4 | `app/core/security.py` uses a bcrypt `CryptContext` with default work factor and no upgrade path. `verify_password` raises `UnknownHashError` on a value that is not a bcrypt hash rather than returning `False`. | The raise is an error-handling defect rather than an exposure by itself, but it turns a malformed stored hash into an unhandled exception on the authentication path that row 1 would add. | Set an explicit cost, add `deprecated="auto"` so hashes re-hash on verify, and decide whether a non-hash is a failure or an error. |
| 5 | `app/main.py` mounts FastAPI's default `/docs` and `/redoc`, which load Swagger UI and ReDoc from a public CDN with no integrity attribute and no version pin. | The full API shape is public, and a CDN compromise executes script in the browser of anyone opening the docs. | Disable the docs routes in production, or self-host the exact asset versions and serve them under a CSP with SRI. |
| 6 | `app/main.py` reads `settings.ALLOWED_ORIGINS`, one of the two authorized touches, which defaults to `[]` — deliberately the least permissive value. It is declared with no validation, so a deployment that sets it to `["*"]` alongside `allow_credentials=True` gets a configuration the browser will reject and no error explaining why. | A misconfiguration, not a vulnerability as delivered. Recorded because the field was added by this programme and its safety depends on the value a deployment supplies. | Validate the origin list at load time and refuse the `"*"` plus credentials combination outright. |
| 7 | `app/services/llm_service.py` sends tweet content to OpenAI with no prompt-injection defence and no scrubbing, and `app/tasks/tweet_processor.py` persists author handles and tweet bodies to Firestore with no minimisation or retention policy. | Untrusted text steers the completion, and personal data accumulates with no expiry. | Constrain the prompt and treat the completion as untrusted output; define what is retained and for how long. |
| 8 | `frontend/src/services/api.ts` interpolates `id` into a request path with no encoding, so `fetchTweetById('1/../7')` resolves to `/tweets/7`. Its base URL evaluates to the literal string `"undefined"`. | Path traversal within the API surface, and every request goes to a relative `undefined/...` path. | Validate the identifier and `encodeURIComponent` the segment. The suite asserts the current `undefined/tweets?...` URL as a fact, so the tests document exactly what a fix changes. |
| 9 | `frontend/src/components/Configuration` renders `API Key` and `Access Token` as `type="text"`, declares no `autocomplete` on any of the four fields, and holds no pending state — so the submit control stays live and a second activation sends a second identical credential write. | Two of four credential values are readable on screen and in any screen share; duplicate writes are unauthenticated and unthrottled. | Mask all four fields, set an `autocomplete` policy, and add pending state or an idempotency key. The E2E suite asserts every one of these as current behaviour, including the double write, so the fix has a ready-made regression test. |
| 10 | `app/api/routes/tweets.py` accepts `skip` and `limit` as unconstrained integers with no maximum. | `limit=2147483647` is accepted. The handler raises before it reads anything today, because it issues SQLAlchemy calls against a Firestore-backed dependency, so this becomes reachable only once that is repaired. | Constrain both to non-negative values with a hard maximum, and add a rate quota. |
| 11 | `app/main.py` installs `CORSMiddleware` and nothing else — no `TrustedHostMiddleware` — so FastAPI's trailing-slash redirect builds its `Location` from the request's own `Host` header. `GET /tweets/` with `Host: attacker.example` answers **307** with `Location: http://attacker.example/tweets`, and the same reflection survives a port, a userinfo prefix, an embedded path segment, a scheme-in-host and an empty host. | An open redirect off a trusted origin (CWE-601): a link to the service's own domain lands the reader on a host the request chose. It needs no authentication, because none of the three operations has any. | Install `TrustedHostMiddleware` with an explicit allowed-host list, or terminate at an edge that canonicalises `Host` before it reaches the app. Every case above is already asserted as current behaviour in `tests/integration/test_route_surface.py`, including `test_application_installs_no_host_validating_middleware`, so a fix will fail those tests by design — update them to the new contract. The Starlette `Host`-handling advisory in row 12 is the same subject seen from the dependency side. |
| 12 | Several `frontend/src` modules log a **raw error object** on their failure paths, and the backend's BigQuery and LLM paths surface provider error text unfiltered. A serialised axios error carries the request, the base URL and the absolute filesystem path of the machine that ran the build; on the configuration path the request body it carries is a credential write. | Whatever the object holds at the moment of failure — project and table identifiers, request bodies, host paths. It is one fixture away from a real credential, and CI retains whatever a report captures. | Log a redacted, structured record rather than the object, and scan retained reports for secrets. The *artifact* half was closed here — `jest-junit` no longer copies buffered console output into `<system-out>`, verified as zero sections and zero host paths in the uploaded file (D316) — but the logging itself belongs to the modules doing it, which §0.8.2 puts out of reach. |
| 13 | `frontend/src/store/index.ts` imports `{ tweetReducer }` and `{ configReducer }`, which the slices never export. The store therefore has no valid reducer: it does not throw, `getState()` returns `{}`, and Redux logs the problem to the console. | Not a security exposure. Listed because it is the reason three page suites are skipped and the reason the E2E harness builds its own store, so a reader auditing this register's neighbours will meet it. | Export the reducers, or import the defaults. Fixing it will make the three skipped page suites runnable. |
| 26 | `frontend/src/components/Configuration` holds all four credentials in React state and renders them as controlled inputs, so React mirrors each value into the `value` **attribute** — including both `type="password"` fields — from first render onwards. All four are therefore present in `outerHTML` in clear text, and the form is never cleared after a successful save, so they stay there for the page's lifetime; the only thing observed to clear them is an unrelated navigation. Row 9 states the field-level masking gap; this row is the DOM-level one, which masking does not affect. | Anything with DOM access reads both secrets in clear text: a browser extension, an injected script, an automation or devtools DOM dump, or an error reporter that serialises the document. Masking is cosmetic against every one of them, and the exposure window is the page's lifetime rather than the write's. The masked fields additionally disclose each secret's length through their dot count, and no reveal control exists, so the value cannot be checked by the person who typed it. | Hold the secret fields as uncontrolled inputs read through refs, or clear the state as soon as a save succeeds, and decide deliberately whether a reveal control exists. The E2E suite types synthetic values only and asserts that none of them reaches the console, so this has a regression test that stays valid across the fix. |
| 27 | The same component's submit path has no in-flight guard, no idempotency key and no `AbortController`. Every activation issues its own `POST` carrying the full credential payload — repeated activation produced one write per activation, several open at once, and two arriving in the same millisecond — and a write abandoned by a route change completes anyway, with its success dialog firing over an unrelated screen. The path it writes to is declared by no backend router, so nothing on the server side authenticates, throttles or de-duplicates it either. | Credential writes are replayable by anyone who can reach the screen, and the only throttle measured anywhere was the browser's own per-origin connection limit. With row 1 there is no identity to attribute a write to, so a duplicate or an abandoned write is indistinguishable from a deliberate one in any log. | Add pending state that disables the control while a write is open, an idempotency key the server can de-duplicate on, and an `AbortController` so navigating away revokes the request — then authenticate and rate-limit the endpoint as part of row 1's authorization work. |
| 28 | The credential write applies no normalisation and no bounds. Validation is native `required` only, so whitespace-only values are accepted and reported as updated successfully with their padding preserved exactly, and no field declares `maxlength`, so four 10,000-character values produce a single 40,068-byte request. | An operator can believe credentials are configured when the stored values are whitespace; the failure then surfaces as an authentication error with nothing pointing back at this screen. The absent length bound is unauthenticated request-size amplification against an endpoint with no rate limit. | Trim and reject blank values, bound each field's length in the markup and again on the server, and cap the accepted body size at the edge. |

## 2. Dependencies — known-vulnerable versions held by an explicit pin

The AAP clause: **§0.6.1** fixes every version as an exact pin against the documented Python 3.9 and Node 16
ceilings, and **§0.9.1** fixes those ceilings. **§0.6.2** separately declines committing a lockfile. A version
change is therefore not an available remedy, and neither is `npm ci`.

The pins are not arbitrary: `pydantic` must stay on 1.x because `app/core/config.py` imports `BaseSettings`
from it, `tweepy` below 4.0 because `StreamListener` was removed, `openai` on 0.x because the code imports
`Completion`, and `httpx` below 0.28 because Starlette 0.27's `TestClient` passes an `app=` shortcut that 0.28
removed. Upgrading any of them changes production behaviour, which is exactly what a test deliverable must
not do.

| # | Exposure | Attacker value | What a human must do |
|---|----------|----------------|----------------------|
| 14 | `backend/requirements-dev.txt` pins versions with published advisories, including the `python-jose` set, `python-multipart`, and Starlette below its fixed releases. `python-jose` is the one pin that is not silent: the manifest declares `python-jose[cryptography]==3.5.0` rather than the 3.3.0 the frozen plan names, above both `CVE-2024-33663` and `CVE-2024-33664`, and states why in one line immediately above it — `# SECURITY: above CVE-2024-33663 / CVE-2024-33664, fixed in 3.4.0.` The pin and the deviation are `DECISION-LOG.md` rows D292 and D363; `backend/tests/test_dependency_closure.py` holds the manifest to the marker and to the installed version. | Depends on the advisory; the JWT ones matter only once row 1 or row 3 makes tokens reachable. | Raise the Python floor above 3.9, then upgrade. Doing so requires re-pinning `pydantic`, `tweepy`, `openai` and `httpx` together and reworking the code that depends on each — a migration, not a bump. |
| 15 | `e2e/package.json` pins `@playwright/test` 1.44.1, whose browser downloader does not verify the TLS chain of the host it fetches from (CVE-2025-59288), and `vite` 4.5.14, which carries its own advisory set. | The downloader is the exposure, and it is already unreachable: no script in this repository invokes it, `browsers:require` and `browsers:verify` both fail closed instead, and CI launches a browser from the runner image. See `DECISION-LOG.md` D111, D129, D236, D264 and D319. | Move to Node 18 or above and upgrade both. The fixed Playwright requires `node>=18`, which the documented ceiling does not permit. |
| 16 | `frontend/package.json` pins versions with advisories in `react-router`, and transitively in `esbuild`, `cookie` and `postcss`. No lockfile is committed, so a transitive resolution is not reproducible between installs. | Advisory-dependent. The absent lockfile is the wider issue: two installs of the same manifest can differ. | Commit a lockfile and upgrade. Both are AAP decisions to reverse, not oversights — §0.6.2 records the lockfile one explicitly. |
| 17 | `blitzy-deck/executive-summary.html` loads reveal.js 5.1.0, Mermaid 11.4.0 and Lucide 0.460.0 from a CDN. Mermaid 11.4.0 has published XSS, prototype-pollution and DoS advisories. | The deck renders no untrusted input — its diagram sources are literals in the file — so the XSS vector has nothing to carry. The residue is that opening it executes third-party script. | Rule 4 fixes these three versions, so the remedy is to change the rule or self-host reviewed copies. `mermaid.initialize` now declares `securityLevel: 'strict'` explicitly — the level 11.4.0 already defaults to, verified in effect at runtime — so the posture is read off the file rather than inherited from a pinned version; it narrows the label sanitiser's allow-list and does not patch the advisories. The exposure and the reason it is bounded are stated on the deck's own closing slide and in the comment above its script tags (D325). |

## 3. Infrastructure and deployment — outside the write surface entirely

The AAP clause: **§0.8.2**, "Excluded directories and files, untouched entirely: `infrastructure/terraform/**`,
`infrastructure/docker/**`, `scripts/**`, `documentation/**`, `.github/workflows/cd.yml`". **§0.8.1** limits
`ci.yml` to "test steps, test-prerequisite install steps, and one new `e2e` job" — so the `e2e` job's artifact
retention was in scope and fixed, while the `build` job's checkout, setup and Codecov steps were not.

| # | Exposure | Attacker value | What a human must do |
|---|----------|----------------|----------------------|
| 18 | `infrastructure/terraform/main.tf` provisions network and storage without the access restrictions and in-transit encryption the resources support. | Broad: this is the deployed perimeter. | Review against the provider's security baseline. Highest-value item in this document, and entirely outside this delivery. |
| 19 | `infrastructure/docker/docker-compose.yml` carries credentials in the file and pins images by mutable tag, including a `postgres:13` service and a `DATABASE_URL` the application does not use — it uses Firestore and BigQuery. | Credentials in a tracked file; an image tag that can be repointed. | Move credentials to a secret store, pin images by digest, and delete the unused service. |
| 20 | `infrastructure/docker/nginx.conf` sets no security response headers and exposes server detail. Both it and the Compose health check target a `/health` route the application does not implement. | Missing defence in depth; a health check that cannot succeed. | Add the header set; implement `/health` or repoint the checks. |
| 21 | `scripts/setup_environment.sh` fetches and executes an installer over the network without verifying it, installs Node 14, and references a `requirements.txt` and `.env.example` that do not exist. | Anyone who can intercept that fetch runs code on the developer's machine. | Verify the download, or install from a signing repository. The script cannot work as written, which limits the exposure to whoever runs it anyway. |
| 22 | `.github/workflows/cd.yml` uses unpinned action references and a placeholder health-check step, and `scripts/deploy.sh` handles credentials in the clear. | A moved tag on a referenced action runs attacker code with deployment credentials. | Pin every action by commit SHA, as the `e2e` job in `ci.yml` already does, and give the job least-privilege `permissions`. |
| 23 | In `ci.yml`, the `build` job's `actions/checkout` does not set `persist-credentials: false`, the job declares no `permissions` block, and its two JUnit uploads inherit the default retention window rather than declaring one. | A credential left in the workspace for later steps; a broader-than-needed token. | Add `permissions: contents: read` and `persist-credentials: false`, and set an explicit retention. The `e2e` job is the worked example — it already does all three. |

## 4. Documentation that overstated the security position

These were **fixed**, and are listed only so a reader who remembers the old wording knows it changed and why.
`README.md`, `backend/tests/README.md`, `frontend/TESTING.md`, `e2e/README.md`, the traceability matrix and
the executive deck each asserted an absolute — no network, no credentials — where the truth is a specific
tested boundary with named residuals. The corrections are recorded in `DECISION-LOG.md` §34 and the boundary
is now stated in each document in the same terms.

Two files that carry the same overstatement were **not** corrected, because they are out of scope:
`documentation/**` is REFERENCE-only under §0.8.2, and `frontend/public/index.html` is named in the same
clause. The design documents describe an authorization model and a `/health` endpoint that the code does not
implement, and the public HTML is an unrelated Create React App template with unsubstituted `%PUBLIC_URL%`
tokens and a third product's title. A reader who takes either as a description of the delivered system will
be wrong about its security posture.

## 5. The executive deck as a served artifact

No AAP clause puts these out of reach — `blitzy-deck/**` is inside the write surface. **Rule 4**, summarised in
AAP **§0.10.4**, is what fixes them: it requires "a single self-contained reveal.js HTML file" with "CDN
versions pinned to reveal.js 5.1.0, Mermaid 11.4.0 and Lucide 0.460.0". Vendoring the assets or moving a pin
would satisfy the security point by breaking the rule, so both rows below are disclosed rather than closed, in
the file's own head comments as well as here (D325). Row 17 above is the third member of this group and is
listed under the dependency pins because that is what fixes it.

| # | Exposure | Attacker value | What a human must do |
|---|----------|----------------|----------------------|
| 24 | The deck's Content-Security-Policy is delivered in a `<meta>` element, and a meta-delivered policy ignores `frame-ancestors` — so the file carries no anti-framing control at all. `script-src` and `style-src` both retain `'unsafe-inline'`, because one self-contained file means the bootstrap and the whole theme are inline and both reveal.js and Mermaid inject style elements at runtime. | A reader served this deck inside someone else's frame is exposed to UI redress (CWE-1021). The `'unsafe-inline'` allowances mean the policy restricts destinations and pins bytes rather than preventing inline execution, so it is not an XSS control for this file. | Serve the deck with an HTTP response `Content-Security-Policy` carrying `frame-ancestors 'none'`, or an `X-Frame-Options` header — neither can come from inside the file. Replacing `'unsafe-inline'` with a hash of the inline bootstrap was measured and rejected: the file is hand-edited and a stale hash blanks the deck silently (D207, D251). |
| 25 | The deck cannot render without reaching `cdn.jsdelivr.net` for three scripts and one stylesheet and `fonts.googleapis.com` / `fonts.gstatic.com` for three font faces — nine requests in total, verified in a browser. The Google Fonts stylesheet carries no integrity digest and cannot: that endpoint varies its body by user agent, so it has no fixed bytes to pin. | Opening the deck discloses the reader's IP address and user agent to two third parties, and the deck is unreadable offline or if either origin is unavailable. The unpinned font stylesheet is the one asset a compromise of that origin could change undetected; it delivers no executable code. | Vendor the four jsDelivr assets and the fonts into `blitzy-deck/`, which contradicts Rule 4's single-self-contained-file form and puts roughly 3 MB of third-party code in git — a rule decision, not an oversight. The four executable/style assets already carry `sha384` digests plus `crossorigin="anonymous"`, so substituted bytes are refused rather than executed. |

---

## What this register does not cover

The exposures above are the ones that were found. This assessment read the delivered tree; it did not
penetration-test a running deployment, and no part of this repository is deployed. Two limits are worth
stating in terms:

- **The application does not run.** `uvicorn app.main:app` fails with `ImportError: cannot import name
  'TwitterService'`, and the frontend cannot be served at all. So no row above has been demonstrated against
  a live instance, and several — rows 2, 10 — are latent behind a defect that would have to be repaired first.
- **The test suite's own boundary is tested, not assumed**, and it is a boundary rather than an absolute. What
  is enforced, and what is not, is stated in `e2e/README.md` and `backend/tests/README.md` rather than
  summarised here.
