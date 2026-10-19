# Part 11. Deployment

The same code runs on the PM's own computer or on a web host. What differs is configuration (`config/server.yaml`,
`config/auth.yaml`, `config/storage.yaml`, a profile) and packaging (`deploy/`). Nothing in the engine, API or UI checks which
host it is on; every difference is a setting the code reads, tested both ways.

**Version 1 is local mode only.** Hosted mode is designed here and built after 1.0 (decisions, 2026-10-11; roadmap, "Not in
1.0"); until then the app refuses to start with `server.mode: hosted`. The sections below say what is built (local) and what
is designed for later (hosted). 11.7 covers installing, updating and restarting, which version 1 does need.

## 11.1 Modes

| | Local (version 1) | Hosted (after 1.0; designed, not built) |
|---|---|---|
| Where it runs | the PM's computer | a server, a container platform, or a machine behind a tunnel, reached at the PM's own domain |
| Who can reach it | only this machine (`127.0.0.1`) | anyone on the internet who gets past sign-in |
| Sign-in | an install token handed to the browser at launch; a password optional | required: at least one provider from 11.4; passwords need a second factor |
| Storage | the workspace folder (database, config, sources) | the same on a persistent volume; export pushed to a private remote |
| Scheduler | runs while the computer is awake; catches up after sleep (6.14) | runs continuously; one scheduler at a time |
| Command-line AI agents | available if installed | only if the image includes them; capability routing falls back otherwise |
| Backups | off-device backup expected; Today and the header nag until one is set up and has succeeded (4.15) | required by the deploy checks |
| Start-up checks | config validation | config validation and the deploy checks (11.5); start is refused if any fail |

## 11.2 Serving under a path, and hiding

The base path is built and tested at the root and under a nested path (end-to-end and API tests). Hiding is designed and not
built (no `server.hide` key yet).

The app can live at the root of its own domain or under a path on a site that serves something else: for example
`https://example.com/admin` while the public site stays at `https://example.com/`. `server.base_path` sets it. What makes that
work without code changes:

- The UI is built with relative asset paths and reads its base path and API address from a small config document the server
  returns, so one build works under any path.
- Every route, redirect, cookie path and generated link is built from `public_url` and `base_path`. Tests run the UI and API
  both at `/` and under a nested path.
- A reverse proxy in front (the host's routing rules, a tunnel, a web server) forwards only that path to the app; the rest of
  the site never reaches it.

**Hiding** (`server.hide: not-found`) makes the app answer 404 to anyone not signed in, except at the sign-in path, which can be
set to something hard to guess. It also sends `noindex`. Hiding cuts noise from scanners; it is not protection. Sign-in (11.4)
and the deploy checks (11.5) protect the app, and hosted mode never relies on hiding alone.

## 11.3 Deploying without code changes

Everything in this part is set through config files, environment variables or flags (4.0), so a hosting platform's settings
page is enough: `COCKPIT_PROFILE=hosted`, `COCKPIT__SERVER__PUBLIC_URL=https://example.com`,
`COCKPIT__SERVER__BASE_PATH=/admin`, and secrets stored as platform secrets and referenced by `env:` names.
`cockpit init --profile hosted` writes a starting profile with every key commented, and `cockpit deploy check` lists what is
missing before the first start. Environment variables for nested keys are built; profiles, `init --profile hosted` and
`cockpit deploy check` are not (hosted, after 1.0).

## 11.4 Sign-in

Built: the install token and its session cookie scoped to the base path (HTTP-only, same-site; the secure flag only when
hosted). Not built, because they are for hosted mode: passwords with a second factor, passkeys, recovery codes, OpenID
Connect, the identity-aware proxy, idle and absolute timeouts, sign out everywhere, CSRF tokens, lockout, the sign-in log and
the Security panel. Not to be confused with the sign-ins an add-on makes to a service such as a mail account (12.1, 7.15).

Sign-in methods are auth providers, an extension point (3.3). The core ships:

- **Install token:** the default in local mode. A random token is created at install and handed to the browser when the PM
  starts the app. Not accepted as the only method in hosted mode.
- **Password with a second factor:** passwords hashed with a memory-hard algorithm (argon2id); one-time codes from an
  authenticator app; passkeys (WebAuthn) as a second factor or instead of the password. Recovery codes shown once at setup.
- **Sign-in provider (OpenID Connect):** any standard provider, configured by issuer, client id and a client secret reference;
  only identities listed in `auth.users` get in.
- **Identity-aware proxy:** for hosts that put their own access gateway in front. The app verifies the signed token the proxy
  adds (signature against the proxy's published keys, issuer, audience, expiry, all from config); it never trusts a plain
  header naming the user. Best combined with an app sign-in, so one misconfiguration doesn't open the app.

**Sessions:** secure, HTTP-only, same-site cookies scoped to the base path; idle and absolute timeouts; sign out everywhere.
Every state-changing request carries a CSRF token. Failed sign-ins are rate limited and locked out per `auth.lockout`. Every
sign-in and failure is logged and shown on the Security panel (7.1).

## 11.5 Deploy checks

Designed; none are built yet, and nothing in version 1 depends on them. Hosted mode, when built, refuses to start unless they
pass, and no check is weakened to get a deployment running.

`cockpit deploy check` runs these; the self-check runs them against both fictional workspaces with a hosted profile; a hosted
server runs them at start and refuses to serve if any fail.

- `public_url` is HTTPS, and requests arrive over HTTPS (directly, or from a trusted proxy that says so).
- At least one provider other than the install token is enabled; passwords require a second factor; at least one user is
  listed.
- The session signing key comes from a secret, is long enough, and isn't a default.
- Every secret reference resolves, and no secret value appears in any config file.
- `allowed_hosts` and `trusted_proxies` are set; CORS is off or limited to listed origins; security headers are on.
- Storage is persistent (the backend reports it) and the last export succeeded; an export remote or backup is configured, or
  the PM has explicitly accepted running without one.
- `public_url` and `base_path` agree with what the proxy forwards (checked by fetching the app's own health address through
  `public_url`).
- No enabled plugin declares a network host or data level the deployment's settings forbid.

Warnings that don't block start: command-line AI agents unavailable, budgets unset, only one sign-in method (no fallback if it
breaks).

## 11.6 Packaging and recipes

Built: `cockpit serve --workspace <path>` in local mode. Not built: start-at-login files, the container image and the two
recipes below (hosted, after 1.0). Installing the app on a person's computer is 11.7.

The engine needs long-running jobs, a file system and git, so it runs as a process or a container, not as short-lived edge
functions.

- **Local:** `cockpit serve --workspace <path>` starts everything and opens the browser with the install token. Optional
  start-at-login service files for each operating system.
- **Container image** (`deploy/container/`): one image with the API, the built UI and the scheduler; runs as a non-root user;
  the workspace on a mounted volume; configured only through environment variables and mounted config. Every hosted recipe
  builds on it.
- **Recipes** (`deploy/<target>/`): one folder per hosting target, with its profile, any platform config files and a
  step-by-step README, plus a test that the profile passes the deploy checks.

First recipes, in order:

1. **Tunnel to a machine the PM owns:** the app runs on the PM's computer or a small always-on box. A tunnel publishes only
   `public_url` + `base_path`, without opening ports, and the tunnel provider's access gateway sits in front (the
   identity-aware proxy provider), plus the app's own sign-in. For example: Cloudflare Tunnel, with Cloudflare Access protecting
   only the `/admin` path of a domain whose public site is served elsewhere. File storage and git stay as they are.
2. **Container host:** the image on a platform with a persistent volume (a small virtual server behind a reverse proxy, or a
   container service). Cloudflare's container service can run the image, but at the time of writing its container disks don't
   persist, so it needs a storage backend other than local files (4.15); check the platform's current limits when writing
   that recipe.

The UI build can also be served from a static host with the API elsewhere (it reads its API address from config), but that is
not a first recipe.

## 11.7 Installing, updating and restarting (version 1)

**Install scripts.** `deploy/install.sh` (macOS, Linux) and `deploy/install.ps1` (Windows) install or update the app from the
package file with `uv tool install --force`. The package carries the built screens, the starting templates, the AI account
catalog and the two fictional demo workspaces, so a person needs no Node and no copy of the repository. A version tag builds the
package, checks that it installs and starts the demo, and attaches it to a release with the scripts and `docs/install.md`
(decisions, 2026-10-11 "The package carries its screens, templates and demos"). A workspace is a separate folder and is never
touched by an install or an update. The scripts exist and are not yet tested.

**One update command.** `cockpit update` is planned (roadmap phase A1, see roadmap-done.md). It pulls, syncs the Python environment without dropping
installed add-ons, installs the web tools, builds, and then says whether a restart is needed, so updating never needs a list of
commands (review of 2026-10-12).

**A starting workspace.** The start is `cockpit init` with no template, then `cockpit serve --open` (`docs/install.md` shows
it; the README still sends a person to a fictional workspace, which roadmap A1 (see roadmap-done.md) corrects). `cockpit demo` makes a labeled demo of fictional data for trying the app; it is the
sandbox, never the start.

**One-click add-on install.** The Add-ons screen installs a pack from its catalog entry: the app downloads the release the
entry names, checks its checksum, installs it beside itself and offers Turn on with the usual restart ask. Update and Remove work
the same way. A private pack's release host takes a read token the person gives once, kept as a secret reference (12.1). Only
packs of pure Python whose needs the app already has are installed this way until phase A2 adds a pack's own libraries (shown
before install, conflicts refused, Remove taking out only what the pack needed). The server side is built; the button is not
yet (7.15). This replaces "the app never installs code into itself" in 3.11.

**The desktop installer (M0).** Signed installers for macOS and Windows that carry everything the app needs (no Python, uv, Node
or terminal), run it in the background, open the setup guide on first run and update themselves. The decision of 2026-10-11
made it the first item after the launch; the later go-forward plan (2026-10-12) places it in phase E, after the packs, and
that plan holds. Not built.
It costs the owner signing certificates and release hosting. A hosted website stays after 1.0.

**The restart rule.** The app restarts only when it must, and only when the person says so (decisions, 2026-10-11). A setting
that everything reads at the moment of use applies at once (`LIVE_KEYS` in `engine/worker.py`: AI accounts, tiers and budgets,
who the person is, names, wording and shortcuts, the accounts counted as ours). Any other change, or a change to the app's code,
is said in words, holds new AI work, and waits for the person to choose Restart now or Later. The app never restarts on its
own. A copy that cannot start itself again says to close and start it.

## 11.8 The end state: an organization install (not in 1.0)

The ultimate goal (owner, 2026-10-13) is a hosted install for a whole organization, a publisher say, where several
people work in one workspace, each with their own role. Nothing here is built in 1.0; it is written now so that what is
built doesn't rule it out.

- **Members are people.** Anyone who signs in is a person on the People list, given sign-in by someone allowed to.
  Sign-in uses the hosted methods (11.4), with `auth.users` naming person ids.
- **Roles are responsibilities.** A role is a named set of what a member may see and do: which packs and screens, which
  projects (all, or only those they take part in), which kinds of records, and which steps (approve a kind of change,
  send or publish, change settings, administer). Roles are assigned per person and, where it differs, per project. A
  writer on the list sees their own books; the publisher's staff see every title.
- **Views per role.** Each member's Today and panels are built from what their role may see. Packs serve roles: a
  writer works mostly in the writing pack's views, the publisher's staff in the publishing pack's, and both meet in the
  shared records through the interfaces between packs (3.9). Packs declare which roles their panels, actions and task
  kinds are for; the core enforces it.
- **One record of who did what.** The ledger records the person behind every change, not only "the person running the
  app", and data levels (5.1) apply per member as well as per AI account.
- **Approvals belong to roles.** "The PM approves" becomes "a member whose role may approve that kind of change". The
  rule that a person approves the exact content of anything outward stays.
- **Learning has an owner.** A member's own corrections teach their own lessons first; organization rules are kept by
  the members allowed to change them (6.21, 6.22).
- **AI accounts and budgets** can be the organization's, with budgets per member and per role (6.16).

What this means today: new core code never assumes there is only ever one person. Whoever acts is a person id (the
person running the app is one of them), screens never hard-code "the PM", and a plugin API addition that would need
changing for roles is designed with roles in mind.

