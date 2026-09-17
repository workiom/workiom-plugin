---
name: workiom-vibe-apps
description: >
  Generate Workiom "vibe apps" — self-contained static web apps, one page or
  several plus any assets they need, that run inside a Workiom tenant at
  {tenant}.workiom.com/vibe/{appId}/ and interact with Workiom lists using
  the logged-in viewer's own session. Use this skill whenever the user asks
  to build, generate, change, or package an internal Workiom page, form,
  tracker, or mini-app — e.g. "I need an app that collects bug reports",
  "make a form that writes to our Leads list", "add a field to the vibe app we
  made". Covers the full pipeline: light intake → schema discovery via the
  Workiom MCP → schema-grounded requirements confirmation → generation →
  validation via scripts/vibe-pack.py → optional in-chat preview → publishing
  through the Workiom MCP. Also edits apps that already exist, by fetching
  their real source rather than regenerating them. The deliverable is a live
  app the user can open, not a file to hand off.
---

# Workiom Vibe App Generator

You produce **vibe apps**: static web apps — one page or several, plus any
assets they need — deployed inside a Workiom tenant. The deliverable of every
session is a **live app the user can open**, published through the Workiom
MCP.

The pipeline is strict and ordered. Do not skip or reorder steps.

```
0. Gate       get_vibe_apps — connected AND beta enabled?         (hard stop if not)
1. Require    light intake: purpose, which list(s), audience
2. Discover   MCP: app → list(s) → fields   (live schema, never memory)
3. Confirm    ~10 schema-grounded content + style questions
4. Generate   system rules below + <app_schema> → files (html/css/js/json, 1+ pages)
5. Validate   python3 scripts/vibe-pack.py <folder> --json  → files map
6. Preview    Artifact side-panel preview vs. mock data, iterate    (when available)
7. Publish    MCP: create_vibe_app / add_vibe_version       → live URL
```

**Changing an app that already exists starts differently.** Fetch its real
source with `get_vibe_app_files(appId)` and edit that, rather than generating a
replacement — see "Editing an app you didn't build in this session". Steps 2
and 5 to 7 still apply; steps 3 and 4 shrink to the change being asked for.

---

## Step 0 — Gate: verify Workiom access FIRST

Before any discovery or generation, call the Workiom MCP tool `get_vibe_apps`.

**`get_vibe_apps`, not `get_apps`.** Both are cheap reads, but only
`get_vibe_apps` passes through the vibe feature gate. A workspace without the
beta answers `get_apps` perfectly happily, so gating on it would let a session
discover, confirm, generate, validate and preview an entire app before hitting
the wall at publish. It also returns the apps that already exist, which is what
tells you whether this request is a new app or an edit of one.

**If the tool is unavailable or the call errors:**

- **STOP. Generate nothing.**
- Tell the user: *"This skill needs the Workiom connector, which ships with
  this plugin. Sign in to it with your Workiom account and ask me again — if
  it isn't listed at all, the plugin may need reinstalling (server URL
  `https://mcp.workiom.com/mcp`)."*
- If the tool exists but returns an auth error, say the connection needs
  re-authentication instead.
- **If a vibe tool answers "This is a private beta, contact support to activate
  it", relay that and stop.** The connector is fine and the account is fine —
  vibe apps just aren't switched on for that workspace. Generate nothing, and
  don't retry or look for another route in; there isn't one.
- **This skill publishes to a live workspace.** For anything experimental,
  keep it off the workspace listing until the user is happy: publish with
  `publish: false` so it stays an unpublished draft, and say that's what you
  did.

**Never generate a vibe app from remembered, assumed, or example field IDs.**
Field IDs are per-tenant and per-list. Any ID not obtained from a live MCP
call in this session is a guess, and a page built on guesses passes every
structural check and then writes garbage — the worst failure mode this skill
has. This rule has no exceptions, including "the user is in a hurry" and
"we looked these up in an earlier conversation".

---

## Step 1 — Requirement (light intake)

Establish just enough to run discovery in Step 2 — asking only for what's
missing. The detailed content/style conversation happens in Step 3, once the
real schema is known; don't front-load it here.

1. **What does the page do?** ("submit bug reports", "request leave", "log a
   customer call")
2. **Which list(s)?** Names suffice — resolved in Step 2. Multi-list apps are
   fine (e.g. read reference data from one list, create records in another).
3. **Who uses it?** Always logged-in tenant users (the platform enforces the
   session); the useful question is which team and what they should see.

If the user can't name the list, show them candidates from `get_apps` /
`get_lists` and let them choose. Do not guess.

---

## Step 2 — Schema discovery (live, every session)

```
get_apps                                → find the app (ask if ambiguous)
find_list_by_name(appId, listName)      → list UUID (on miss it returns
                                          availableLists — offer those)
get_list_info(listId)                   → fields: id, name, dataType,
                                          isRequired, isSystemField,
                                          isComputed, isReadOnly,
                                          staticListValues
```

Repeat per list for multi-list apps.

**Two failure modes to guard against, both observed in production:**

- **Trust the numeric `dataType`, never `typeName`.** The MCP has mislabelled
  `dataType: 16` (Status) as "Location" and "Field Lookup". The numeric code
  plus `staticListValues` are authoritative.
- **Copy option labels character-for-character** — spaces, pipes, emoji, case.
  `"Feature | Improvement"` has spaces around the pipe; a normalised version
  is silently ignored by the API.

Discovery's output — every field's id, name, dataType, and (for selects) its
verbatim option labels — is the raw material for Step 3's questions. Don't
ask the user to choose fields or presentation before this step runs.

---

## Step 3 — Confirm (schema-grounded, ~10 questions)

Now that the real fields are known, have the detailed requirements
conversation grounded in them — not generic questions asked blind. Ask an
adaptive checklist; skip anything the user already answered unprompted.
Roughly half is about content (what the app does with this data), half about
style (how it presents it) — ask them together, per field or view, using
each field's real name and (for selects) its real option labels, never
abstractions.

**Content — what the app does with the real data:**

1. Walk the discovered fields with the user — which appear on the page, which
   stay out. Apply the exclusion defaults first, before asking:
   `isSystemField` (Creator, dates), `isComputed`/`isReadOnly`,
   lookups/rollups, workflow fields (Status, Assignee, Sprint, approvals —
   server-defaulted or team-managed), and Linked List fields unless the user
   explicitly needs them and understands they take arrays of record IDs.
2. **Operations** — create-only, or also browse/edit/search/delete-one?
3. For each `StaticSelect`/`Status`/`MultiStaticSelect` field: which of the
   discovered options are relevant, or offer all of them?
4. **Cross-list lookups**, when multiple lists were discovered — does one
   list feed reference data into another?
5. **Validation/business rules** beyond each field's own `isRequired`.

**Style — how those specific fields/views should look:**

6. **Page/nav structure & view pattern** — one page, or separate views (e.g.
   a browse view + a detail/edit page + a create form)? For any list/browse
   view, which presentation actually fits the data — table, Kanban board,
   calendar, card gallery, or simple list (see "Choose the display pattern"
   below)? Propose one based on the schema rather than defaulting to a table.
7. **Field presentation** for the fields just chosen — e.g. a `Status` field
   as a dropdown vs. a segmented control; a `MultiStaticSelect` as checkboxes
   vs. tag input.
8. **Branding & theme** — accent colour, density, any existing style to
   match; propose a subject-appropriate visual theme (see "Theme the design
   to the app's subject" below) unless they already have a direction.
9. **Language** — English, Arabic (RTL), or bilingual.
10. **Feedback** — confirmation behaviour, error handling, empty states.

Once answered, build the schema block Step 4 generates against:

```xml
<app_schema>
  <tenant subdomain="..." />
  <app id="..." name="..." />
  <list id="<uuid>" name="...">
    <field id="<int>" name="..." type="Text|LongText|Number|Date|DateTime|StaticSelect|MultiStaticSelect|Status|Email|Phone|URL|User|People|File" required="true|false">
      <option>verbatim label</option>   <!-- StaticSelect/Status only -->
    </field>
  </list>
  <!-- more <list> elements for multi-list apps -->
</app_schema>
```

---

## Step 4 — Generate

Produce whatever files the structure confirmed in Step 3 actually needs.
Inline `<style>`/`<script>` in a single `index.html` is still the right call
for a simple one-shot form; split into `styles.css`, `app.js`, additional
`.html` pages, or `*.json` config whenever that's a better fit. Don't default
to one file, and don't split for its own sake — let Step 3 question 6's
answer decide. Reference any split-out file by **relative path**.

### Multi-page apps

The platform serves any file in the bundle at its own path under
`{tenant}.workiom.com/vibe/{appId}/...` — the bare app URL resolves to
`index.html`, but a second file like `settings.html` is directly reachable
and loads as a real page. So a genuine multi-page app — separate `.html`
documents linked by relative `<a href="page.html">` — works today. Rules
that make it actually work under the platform's constraints:

- **`index.html` is the entry point.** Any other `.html` file is linked to
  with a relative path, exactly like an asset.
- **No server includes.** There's no templating step, so each `.html` file
  must be a complete, standalone document. Share `styles.css` and a common
  `app.js` (auth helpers, shared fetch logic) via `<link>`/`<script src=>`,
  but nav/header markup itself is duplicated per page.
- **Cross-page state travels via URL query params** — e.g.
  `detail.html?id=<recordId>`. JS variables reset on a full page navigation,
  and `localStorage`/`sessionStorage` are already banned, so query params
  are the only channel for passing a selected record, a filter, or a wizard
  step from one page to the next.
- **Auth is checked on every page independently** — each page load is a
  fresh document; run the same `getCookie`/`workiomHeaders()` check and
  render the same logged-out state on each one.
- Every platform constraint below (CSP, relative paths, allowed extensions,
  `textContent`-only) applies **per file**, not just to `index.html`.

### Platform constraints (violations = broken page, not rejected upload)

- **No external resources.** The serving CSP is `default-src 'none'` with
  inline script/style and same-origin connects only, plus Workiom's own API
  hosts. No CDNs, no Google Fonts, no analytics, no remote images. System font
  stacks; inline SVG or emoji for icons; hand-rolled JS.
- **Workiom's API hosts are allowed for `fetch`/XHR only, not `<img>`.**
  The CSP grants them under `connect-src`; `img-src` stays at the `default-src
  'none'` default. A direct `<img src="https://api.workiom.com/...">` is
  silently blocked before it reaches the network (confirmed via DevTools —
  zero bytes transferred, no error surfaced to JS). For file thumbnails and
  downloads, fetch the bytes with `workiomHeaders()` and use a blob URL — see
  "File attachments" below.
- **The API host is not always `api.workiom.com`.** A workspace can be served
  by its own shard, and only that shard holds its data. The host is resolved at
  runtime — see "Calling the API". Hardcoding one is the same class of mistake
  as hardcoding a tenant id.
- **Relative asset paths only.** `src="assets/x.jpg"` — never a leading `/`
  (resolves outside the app and 404s), never `/vibe/{appId}/…` (breaks on
  rename), never a `<base>` tag (CSP `base-uri 'none'` ignores it).
- **Allowed file types**: `html css js json svg png jpg jpeg webp gif ico
  woff woff2 txt map`. Limits: ≤200 files, ≤5 MiB per file. The platform
  accepts ≤25 MiB in total, but publishing goes through an MCP tool call,
  which caps a bundle at **4 MiB total** — build to that, not to 25 MiB.
- **No browser storage** (`localStorage`/`sessionStorage`/IndexedDB), no
  `eval`, no `new Function`. State lives in JS variables and in Workiom.

### Authentication — exact pattern, no variations

The viewer is already logged in; the session lives in two cookies readable by
page JS. Use exactly:

```js
function getCookie(name) {
  for (const part of document.cookie.split("; ")) {
    const i = part.indexOf("=");
    if (i > -1 && part.slice(0, i) === name)
      return decodeURIComponent(part.slice(i + 1));
  }
  return null;
}

function workiomHeaders() {
  const token = getCookie("Abp.AuthToken");
  const tenantId = getCookie("Abp.TenantId");
  if (!token || !tenantId) return null;   // caller renders the logged-out state
  return {
    "Content-Type": "application/json",
    "Accept": "text/plain",
    "X-Requested-With": "XMLHttpRequest",
    "Authorization": "Bearer " + token,
    "Abp.TenantId": tenantId,
    "X-Workiom-Tenant-ID": tenantId,
    "Client-Type": "Web"
  };
}
```

Hard rules:

1. Never hardcode a token, API key, tenant id, or API host — cookies are the
   only source for the first three, and `apiBase()` for the last.
2. The token appears **nowhere** except the `Authorization` header: not in
   `console.log`, not in the DOM, not in errors, not in debug panels (show
   response bodies, never request headers).
3. `workiomHeaders()` returning null → send the viewer to sign in. Fire no
   requests first.
4. HTTP 401 or `unAuthorizedRequest: true` → the session expired while the page
   was open. Send the viewer to sign in. Never retry the request, and never
   loop.

Both cases use the same helper, and every generated app includes it verbatim:

```js
let redirectingToLogin = false;

function redirectToLogin() {
  if (redirectingToLogin) return;        // a page firing several requests at
  redirectingToLogin = true;             // once must not redirect several times

  const returnUrl = encodeURIComponent(location.pathname + location.search);
  location.replace("/account/login?returnUrl=" + returnUrl);
}
```

Three details that matter:

- **`location.replace`, not `location.href`.** The expired page must not stay
  in history — otherwise Back returns the viewer to a dead page that
  immediately bounces them out again.
- **Build the return URL from `location.pathname`**, never from anything the
  page received from elsewhere. A return URL taken from input is an
  open-redirect.
- **Say something before you go.** A viewer who has typed into a form loses it
  on redirect. Show "Your session expired — taking you to sign in…" and
  redirect a moment later, rather than yanking the page away mid-sentence.
  If the form holds unsaved input, say that too.
5. Refuse to build anything that collects credentials — the session already
   exists; a password field on a vibe page is indistinguishable from phishing.

### Calling the API

**Resolve the base first — never hardcode it.** A workspace can be served by
its own API host (a shard), and that host is the only one holding its lists;
calling the wrong one fails with "not found" errors that look like a bad
`listId`. The page finds its own host from its own hostname, using an
anonymous endpoint on the central host. Every generated app includes this
verbatim:

```js
let apiBasePromise = null;

function apiBase() {
  if (apiBasePromise) return apiBasePromise;

  // A workspace on *.workiom.com is identified by its subdomain; one on its
  // own domain, by the origin. The backend prefers tenancyName when both are
  // sent, so send exactly one.
  const host = location.hostname.toLowerCase();
  const body = host.endsWith(".workiom.com")
    ? { tenancyName: host.split(".")[0] }
    : { customDomain: location.origin };

  apiBasePromise = fetch("https://api.workiom.com/api/services/app/Account/IsTenantAvailable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  })
    .then(r => r.json())
    .then(j => {
      // apiUrl is set only for a workspace on its own shard; serverRootAddress
      // names the host serving everyone else. Both come from Workiom, so
      // neither is a guess.
      const base = j?.result?.apiUrl || j?.result?.serverRootAddress;
      if (!base) throw new Error("Workiom did not report an API host for this workspace.");
      return base;
    })
    .catch(err => {
      apiBasePromise = null;   // a cached rejection would make any Retry fail instantly
      throw err;
    });

  return apiBasePromise;
}
```

Three rules about it:

- **Never fall back to `https://api.workiom.com` when the lookup fails.** For a
  sharded workspace that host is the wrong server; calling it anyway turns a
  clear failure into a page that appears to work and shows no data. A failed
  lookup renders the page's error state, the same as any other failed request.
- **Resolved once per document, held in a variable.** `localStorage` is banned
  (see platform constraints), and every page of a multi-page app is a fresh
  document, so each one resolves for itself — the same way each one re-checks
  auth.
- **Await it before building any URL**: `const base = await apiBase();`, then
  `fetch(base + "/api/services/app/...")`. It is the only request in the page
  that does not use `workiomHeaders()` — it is anonymous by design, and sending
  a session token to it would be pointless.

All other calls use `workiomHeaders()`. Paths below are relative to the
resolved base.

**`X-Api-Key` must never appear in a generated page.** Workiom's API guide documents it for server-to-server use; it is a tenant-wide credential and putting it in a page exposes it to anyone who opens devtools. The page uses the viewer's session instead.

| Operation | Call |
|---|---|
| Read records | `POST /api/services/app/Data/All` body `{listId, maxResultCount, skipCount}` → `result.items[]`, `result.totalCount` |
| Create | `POST /api/services/app/Data/Create?listId={listId}` body flat `{"<fieldId>": value}` → `result.id` |
| Update | `PUT /api/services/app/Data/UpdatePartial?listId={listId}&id={recordId}` body only changed fields; `null` clears |
| Delete one | `DELETE /api/services/app/Data/Delete?listId={listId}&id={recordId}` |
| Comment | `POST /api/services/app/AdvancedComment/Comment?commentAsPlainText=true` body `{listId, recordId, comment}` |
| Read comments | `GET /api/services/app/AdvancedComment/GetAll?listId={listId}&recordId={recordId}` |
| Users (pickers only) | `GET /api/services/app/User/GetAll?isActive=true` |
| Field schema | `GET /api/services/app/Fields/GetAll?listId={listId}&withSystemFields=true` |
| Current user | `GET /api/services/app/Session/GetCurrentLoginInformations` → `result.user.id` (needed for File uploads, see below) |
| Upload file | `POST /File/Upload` — **no** `/api/services/app` prefix, unlike every other row in this table; this is a plain controller, not the ABP dynamic proxy. Multipart body, field name `files` → `result[]`, each item `{fileName, fileType, fileToken, hasThumbnail, fileUrl, thumbnailUrl}`. This is **not** the write shape — see below. |
| Download / thumbnail | `GET /File/DownloadFile?id={_id}&preview=false` / `GET /File/DownloadThumbnail?id={_id}&preview=false` — same no-prefix rule as Upload. **Use `_id`, not `FileToken`** — see below. |

Reads reflect the viewing user's own permissions — a page cannot surface records they couldn't already see. Paginate `Data/All` by incrementing `skipCount`. Records carry `_id` (a string).

**Value formats — writing and reading are NOT symmetric. This is the top source of silent bugs.**

| Type | Send | Receive |
|---|---|---|
| Text / Email / Phone / URL | string | same |
| Number | `42` (number, not `"42"`) | same |
| Date / DateTime | ISO string | same |
| Boolean | `true`/`false` | same |
| StaticSelect / Status | **the label, verbatim** | `{id, label, order}` |
| MultiStaticSelect | array of labels | array of `{id, label}` |
| User / People | email / array of emails | user object(s) |
| Linked List | array of record `_id` strings | array of record objects |
| File | array of transformed file objects (see below) | array of file objects — **different shape, see below** |

To display a select read from a record use `value.label`; to write it back send `value.label`, never the object and never the option `id`. Omit optional fields left empty — no `null`, no `""`.

**File attachments.** Upload with a plain multipart POST to `File/Upload`. Same origin, so no CSP issue — but note this endpoint (and the download/thumbnail endpoints below) do **not** carry the `/api/services/app` prefix every other call in this doc uses; they're a separate plain controller, not the ABP dynamic proxy. Calling `/api/services/app/File/Upload` 302-redirects to a 404 instead of failing cleanly, and is the most common way this silently breaks.

```js
async function uploadFile(file) {
  const headers = workiomHeaders();
  if (!headers) { redirectToLogin(); return null; }
  delete headers["Content-Type"];          // let the browser set the multipart boundary

  const body = new FormData();
  body.append("files", file);

  const res = await fetch(`${await apiBase()}/File/Upload`, {   // NOT /api/services/app/File/Upload
    method: "POST", headers, body
  });
  const json = await res.json().catch(() => null);
  if (res.status === 401 || json?.unAuthorizedRequest) { redirectToLogin(); return null; }
  if (!json?.success) throw new Error(json?.error?.message || "Upload failed");

  return json.result[0];   // { fileName, fileType, fileToken, hasThumbnail, fileUrl, thumbnailUrl } — NOT the write shape, see below
}
```

**The upload response is not the write shape.** `Data/Create`/`Data/UpdatePartial` need an explicit transform for a File field — confirmed via DevTools against the real frontend's own write payload. Four fields (`AnonymousForm`, `ExpiryDate`, `IsPermanent`, `UserId`) exist only in the write shape and are never present in the upload response:

```js
function toFileFieldValue(uploaded, originalFile, userId) {
  return {
    _id: uploaded.fileToken,
    AnonymousForm: false,
    ContentType: uploaded.fileType,
    ExpiryDate: null,
    FileName: uploaded.fileName,
    FileToken: uploaded.fileToken,
    FileUrl: uploaded.fileUrl,
    HasThumbnail: !!uploaded.hasThumbnail,
    IsPermanent: true,
    Size: originalFile.size,   // not returned by the API — carry from the original browser File object
    ThumbnailUrl: uploaded.thumbnailUrl,
    UserId: userId              // see below — never comes from the upload response
  };
}
```

Fetch `userId` once per session (not per upload) via `GET /api/services/app/Session/GetCurrentLoginInformations` — this one *does* use the normal `/api/services/app` prefix — read `result.user.id`, and cache it. Send an array of `toFileFieldValue(...)` results as the File field's value in `Data/Create`/`Data/UpdatePartial`, the same way any other field value is sent. Do not build the presigned permit → PUT → confirm flow — it's a separate, cross-origin path meant for the main app, not vibe pages.

**Reading a File field back is a different, PascalCase shape — do not reuse the write shape.** A record read from `Data/All` returns each attachment as:

```json
{
  "_id": "...",
  "FileToken": "...",
  "FileName": "...",
  "ContentType": "...",
  "Size": 12345,
  "HasThumbnail": true,
  "IsImage": false,
  "FileUrl": "...",
  "ThumbnailUrl": "..."
}
```

Always an array, even for one file. **Never point an `<img src>` or `<a href>` directly at the API host** — the CSP's `img-src` stays at the default `'none'` (only `connect-src` allows Workiom's API hosts, so a direct `<img>` is silently blocked before it hits the network, zero bytes transferred), and a plain link-click download can't be relied on to carry the session cookie across the navigation. `FileUrl`/`ThumbnailUrl` on the object above are always minted `inline` and are not download links either way.

**Use `_id`, not `FileToken`, for every download/thumbnail call — this is the single most common way file read-back breaks.** `DownloadFile`, `DownloadThumbnail`, and `GeneratePublicDownloadUrl` all resolve the file server-side via a lookup keyed on the file's Mongo document id — despite parameter names like `id`/`fileToken` suggesting otherwise. `_id` and `FileToken` are **different values** once a file has gone through a record write (only `FileToken` survives from the original `Upload` response into the write payload; `_id` is assigned server-side when the record's File field value is persisted). Passing `FileToken` gets back a clean, misleading `"File not found!"` — not a network or auth error, so it's easy to mistake for something else being wrong.

For a **thumbnail or inline preview**, fetch the bytes with the same `workiomHeaders()`-authenticated `fetch()` used for every other call and convert the response to a blob:

```js
async function fetchFileBlob(file, { thumbnail = false } = {}) {
  const headers = workiomHeaders();
  if (!headers) { redirectToLogin(); return null; }
  delete headers["Content-Type"];

  const id = file._id || file.FileToken;   // _id first — see above
  const action = thumbnail ? "DownloadThumbnail" : "DownloadFile";
  const res = await fetch(`${await apiBase()}/File/${action}?id=${encodeURIComponent(id)}&preview=false`, { headers });   // no /api/services/app prefix
  if (res.status === 401) { redirectToLogin(); return null; }
  if (!res.ok) throw new Error(`${action} failed (${res.status})`);

  return URL.createObjectURL(await res.blob());
}
```

Use the resulting blob URL as `img.src` for a thumbnail, or as the `href` of a throwaway `<a download>` `.click()`ed programmatically.

For a **real forced download** (a "Save As" prompt rather than inline display), `DownloadFile`'s disposition isn't controllable — use `GeneratePublicDownloadUrl?forceDownload=true` instead. Unlike `Upload`/`DownloadFile`, this one *does* carry the `/api/services/app` prefix, and its response is the normal `{success, result: {url, expiryDate}}` envelope, not a bare object. The URL it returns is a presigned link to a different origin (S3), so **don't `fetch()` it** — that hits the same `connect-src` wall as a direct `<img>`. Navigate to it instead — a plain `<a>` click, not `window.open()`. Because the S3 response carries `Content-Disposition: attachment`, the browser downloads the file without ever leaving the current page, so there's no tab to manage and no pop-up-blocker risk either:

```js
async function downloadFile(file, fileName) {
  const id = file._id || file.FileToken;
  const headers = workiomHeaders();
  if (!headers) { redirectToLogin(); return; }

  const res = await fetch(`${await apiBase()}/api/services/app/File/GeneratePublicDownloadUrl/${encodeURIComponent(id)}?forceDownload=true`, { headers });
  if (res.status === 401) { redirectToLogin(); return; }
  const data = await res.json().catch(() => null);
  if (!res.ok || data?.success === false) throw new Error(data?.error?.message || `HTTP ${res.status}`);
  const url = data?.result?.url;
  if (!url) throw new Error("Response had no result.url");

  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
```

**Response envelope — HTTP 200 does not mean success:**

```js
const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(payload) });
const json = await res.json().catch(() => null);

if (res.status === 401 || json?.unAuthorizedRequest) {
  redirectToLogin();                     // session expired — see the auth rules
  return;
}

if (!res.ok || !json || json.success === false) {
  throw new Error(json?.error?.message || ("Request failed (" + res.status + ")"));
}
```

The expiry check comes **before** the generic error check on purpose: an expired
session is not a failure to report to the viewer, and rendering "Request failed
(401)" next to a redirect is noise.

Surface `error.message` — it's human-readable ("Summary field is required").

**Field discipline:** only ids from the `<app_schema>` block; never invent one, never guess at fields that "probably exist". Ids are per-list — in multi-list apps keep each payload to its own list's ids.

### Code quality

- `textContent` for every user-supplied or API-returned string. **Never
  `innerHTML` with interpolated data.** Mixed formatting → `createElement`.
- Submit buttons disabled while in flight, re-enabled in `finally`.
- Client-side validation of `required` fields; focus the first offender;
  errors in a visible page element, never `alert()`.
- Loading, empty, and error states for everything asynchronous.
- Semantic elements, labelled inputs, adequate contrast; usable at 360 px.
- Arabic/bilingual requests: `dir="rtl"` handling done properly, not bolted on.

### Visual design — the bar is "beautiful," not merely "clean"

Default to polished, professional design work, not the bare-bones
utilitarian look. Internal tools don't have to look like internal tools.
Within the platform's constraints (system font stacks only; no external
fonts/CDNs/images — everything inline or hand-rolled), still invest in:

- **A considered palette**, not one flat accent colour — a primary, a
  couple of supporting neutrals, and semantic colours for status/severity
  (success/warning/danger) that read clearly against the background, with
  contrast actually checked, not assumed.
- **Typographic hierarchy** — distinct weights/sizes for headings, labels,
  body text, and meta text; comfortable line-length and line-height.
- **Depth and rhythm** — a consistent spacing scale, subtle shadows or
  borders for elevation (cards, panels), rounded corners used deliberately.
- **Motion where it earns its keep** — CSS transitions on hover/focus/state
  changes, a loading spinner or skeleton instead of a bare "Loading…"
  string. No animation libraries; hand-rolled CSS only.
- **Every state designed, not just the happy path** — empty, loading, and
  error states get the same visual care as the populated view.

If the app shows charts, KPI tiles, or other data visualisation and the
`dataviz` skill is available in this session, load it for palette and layout
guidance before building them.

### Theme the design to the app's subject

Infer a visual theme from what the app is actually about — the app/list
name and purpose from Step 1, not a generic look bolted on afterward. A
cinema-tracking app can lean into a theatrical palette and film-reel motifs
(inline SVG, never stock imagery); a plant-care tracker can lean botanical;
an expense tracker can stay crisp and financial. Propose the theme as part
of Step 3 question 8 and go with it unless the user asks for something
plainer or names their own direction — state the assumption in one line
rather than asking permission for an obvious, low-risk aesthetic choice.

### Choose the display pattern the data actually fits — not always a table

A table is one option, not the default. For any list/browse view, pick
based on what the fields actually are:

- **Kanban board**, grouped by a `Status`/`StaticSelect` field with a
  handful of options — workflow-style tracking (tickets, orders, requests).
- **Calendar view**, keyed off a central `Date`/`DateTime` field —
  scheduling, bookings, events.
- **Card/gallery grid** — records with a strong visual identity (a title,
  an image-like field, a short description) where scanning cards beats
  scanning rows.
- **Table** — genuinely tabular data: many comparable fields per record,
  where sorting/scanning across columns matters more than any single
  record's visual identity.
- **Simple list** — few fields, lightweight browsing.

Recommend one based on the schema and confirm it as part of Step 3 question
6, rather than defaulting to a table because it's the easiest to generate.

### Editing an app you didn't build in this session

Don't regenerate an existing app from scratch to change one thing — that
silently discards every customisation you can't see. Pull the real source
first:

```
(Step 0 already listed them)       → find it there
get_vibe_app_files(appId)          → the live version's files, as a files map
   edit the files                  → keep everything not being changed
add_vibe_version(appId, ...)       → publish the edit
```

Step 2's schema discovery still runs — the fetched source tells you what the
app does, never what the list currently contains.

If `get_vibe_app_files` reports no stored bundle, the app predates bundle
archiving and its source cannot be recovered. Say so before rebuilding, and
confirm the user accepts losing whatever the original had.

### Iterating

Change requests return the **complete updated file(s)** — never a fragment or
diff. Preserve everything the user didn't ask to change. Then re-run Steps 5
to 7 in order — validate the edited files, refresh the preview artifact if one
is live and let the user confirm again, then publish. A version is a whole
bundle, not a patch, so an edited page means a new version carrying every file.

---

## Step 5 — Validate (mandatory, never skipped)

Validate the real bundle from Step 4 — never the preview build from Step 6,
which contains mock data and inlined scaffolding that must never ship.

Write the files to a folder named after the app id
(`^[a-z0-9][a-z0-9-]{0,63}$`, lowercase; not `studio`, `_api`, `_preview`,
`_health`, `admin`), then:

```bash
python3 scripts/vibe-pack.py ./<appId>/ --json
```

- **Exit 0** → the files map is on stdout, ready for Step 7. Diagnostics go to
  stderr, so stdout is safe to parse.
- **Exit 1** → violations listed with file:line, and stdout stays empty.
  **Fix them and re-run.** Never publish files the script rejected, never
  hand-assemble the files map to skip a FAIL, never ask the user to ignore one.
- **WARN lines** need a human glance, not a fix — e.g. `Abp.AuthToken`
  flagged inside the legitimate `getCookie` pattern is expected.

This is the only place the content rules are enforced — the backend checks
structure and size, not `innerHTML` or external resources. Skipping it ships an
unsafe page.

---

## Step 6 — Preview (when available)

Show the user the app in the chat before it goes to Workiom, if this session
has the Artifact tool. If it doesn't, say so in one line and skip straight to
Step 7.

Preview the bundle Step 5 already validated. Previewing first would spend the
user's approval on files that can still be rejected, and any fix would mean
re-previewing and asking again.

**This is a preview, not the live page.** An Artifact cannot reach the real
Workiom API — its CSP blocks requests to any external host — and cannot read
the real session: the `Abp.AuthToken`/`Abp.TenantId` cookies are scoped to
the tenant's `workiom.com` origin, not claude.ai's. So the preview runs the
same markup and logic against **synthetic sample data** instead of the real
API — never the user's real tenant data.

1. **Build a preview bundle, not the real one.** Concatenate the actual
   generated HTML/CSS/JS from Step 4 into one self-contained file — same
   markup, same logic, just packaged to satisfy the Artifact tool's
   no-external-resources/inline-everything requirement. Load the
   `artifact-design` skill first (the Artifact tool's own precondition) and
   pick a favicon.

   **Multi-page apps need handling here.** An artifact is a single document,
   so a relative `<a href="page.html">` has nothing to navigate to — left
   alone, the preview dies on the first nav click. Either:

   - inline each page as a hidden container and intercept clicks on relative
     `.html` links to swap which one is visible, keeping the same nav markup
     the real app uses; or
   - preview the entry page only, and say plainly which pages aren't covered.

   Take the first option when the pages share a layout; take the second when
   faking navigation would misrepresent how the real app behaves. Never show
   a multi-page preview without saying which of the two you did.
2. **Stub the network.** Replace calls to the endpoints in "Calling the API"
   above with a small fetch-intercepting shim. **Stub `apiBase()` too** — it
   is a real request to `api.workiom.com`, which the Artifact's CSP blocks, so
   an unstubbed one leaves every `await apiBase()` pending forever and the
   preview renders empty with no error. Have it resolve to any placeholder
   string; nothing in the preview dereferences it. Generate sample records
   shaped by `<app_schema>` — cycle through each `StaticSelect`/`Status`
   field's real discovered option labels, plausible dummy values for other
   types — enough rows to populate list/browse views. Simulate
   create/update/delete in memory so the preview is genuinely interactive
   (submitting a form appears to succeed, a new row shows up) without
   touching Workiom.
3. **Label it unmistakably.** A small fixed banner — "Preview — sample data,
   not connected to Workiom" — so it's never mistaken for the live page or
   real tenant data.
4. Publish it with the Artifact tool so it renders in the chat's side panel,
   then **explicitly ask**: "Here's a preview — anything you'd like changed
   before I publish it to Workiom?" Don't just show it and wait silently.
5. **Do not proceed to Step 7 without an explicit go-ahead.** A change
   request means: apply it to the **real Step 4 files**, re-run Step 5 on
   them, rebuild the preview, republish the same artifact path (it redeploys
   in place), and ask again. Only an explicit "looks good" / "publish it" /
   equivalent moves on to Step 7 — silence or an ambiguous reply is not
   consent.
6. **Never publish the preview build.** The mock-fetch shim, the inlined
   single-file packaging, and any faked navigation are disposable scaffolding
   for this step only. Step 7 publishes the original, unshimmed, multi-file
   bundle validated in Step 5.

---

## Step 7 — Publish

Pass the files map from Step 5 straight to the MCP. Never build a zip; the
tools take the files themselves.

**New app:**

```
create_vibe_app(appId, name, icon, color, description, files)
```

**Updating an app that already exists** — check with `get_vibe_apps` first:

```
add_vibe_version(appId, versionName, files)
```

Both publish immediately by default and return the version that went live.
Pass `publish: false` only when the user explicitly wants a draft they will
review before it goes live.

Then tell the user where it is: `{tenant}.workiom.com/vibe/{appId}/`, which
opens for any logged-in user in that workspace.

Other operations, when asked:

- `get_vibe_app(appId)` — version history and which version is currently live
- `get_vibe_app_files(appId, version?)` — read a version's source back as a
  files map, defaulting to the live one
- `publish_vibe_version(appId, version)` — **roll back** by publishing an
  older version number; the files are already stored, so this is instant and
  cannot leave the app broken
- `update_vibe_app(appId, ...)` — change the app's name, icon, colour or
  description. Partial: omitted fields keep their current value. This is
  listing metadata only; it cannot change the page's design, which takes a new
  version.

If publishing fails, say what failed and stop. Do not fall back to handing the
user files — a rejected bundle is a bug to fix, not a package to deliver.

---

## Refuse, briefly and clearly

- Reading, displaying, exporting, or transmitting the auth token/cookies
- Credential-collection UI of any kind
- External scripts/resources, or sending data to non-Workiom origins
- **Schema mutation** — `Fields/Create|Update|Delete`, `Lists/Create|Delete`, `Apps/Create`. A vibe app consumes a schema, never reshapes one.
- **Roles or permissions** — `Role/*`, `Permission/GrantMembers`. This is privilege escalation by prompt.
- **Bulk destructive loops** — `Data/Delete` in a loop, or "update everything matching". A single delete with explicit confirmation is fine; a batch is not.
- **Publishing the Step 6 preview build** — its mock data, fetch shim, and single-file inlining are for the chat preview only and must never reach Workiom.
- Generating without live schema discovery (see Step 2)

For anything else ambiguous, make a sensible choice and state the assumption
in one line rather than stalling.
