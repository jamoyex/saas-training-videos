# Authenticated sessions: the human operator signs in, the agent records

Most SaaS training needs a logged-in app. The rule is simple: **a human operator signs in; the agent never sees, types,
stores or asks for credentials.** The recorder keeps each login in its own browser profile, so the person signs in once
and every later take reuses the session.

## 1. Roles
| Human operator | Agent |
|---|---|
| owns the account; chooses/creates the demo workspace and demo user | prepares the profile and opens the browser |
| types password, 2FA code, passkey, SSO, solves CAPTCHAs, approves security prompts | waits; never reads the screen while credentials are entered |
| switches to the demo workspace, dismisses first-run popups | verifies *where* the browser is (URL + title only) and starts work |
| approves takes that change data; does identity checks / payments if ever needed | stops at confirm buttons for anything paid or irreversible |

## 2. The hand-off, step by step
1. **Agent** picks a profile name per account (`acme-demo`, `acme-admin`) and runs:
   ```
   python3 scripts/pw_record.py login acme-demo https://app.acme.com/login --until "/dashboard"
   ```
   A visible Chrome window opens on the sign-in page. With `--until`, the command waits (up to 10 min, `--timeout`) until
   the URL contains `/dashboard` — i.e. the person is in. Without it, ask the person to say "done".
2. **Agent tells the operator**, in plain words: "A Chrome window titled <app> is open. Please sign in there yourself
   (including any code or approval), switch to the <demo workspace>, close any welcome popups, and leave the window
   open. Tell me when you see the dashboard." Never ask them to paste anything into the chat.
3. **Operator** signs in in that window (not their everyday Chrome — the recording browser is a separate profile).
4. **Agent verifies** without reading content: `python3 scripts/pw_record.py status acme-demo` → URL + title. If it shows
   a login page, MFA page or the wrong workspace, ask the operator again. Then explore and record as usual.
5. When the project is done: `pw_record.py close acme-demo`; to log out completely, `pw_record.py cli acme-demo delete-data`
   (or delete `~/.training-video/pw-acme-demo/`).

## 3. Special cases
| Case | What to do |
|---|---|
| **SSO / "Sign in with Google/Microsoft"** | the operator completes the provider's popup in the same window; the session lands in the profile |
| **Magic link by email** | the operator copies the link from their email and pastes it into the *recording* window's address bar (not their usual browser) |
| **Passkeys / hardware keys / phone approval** | operator only; if the OS prompt appears, they handle it |
| **CAPTCHA / bot checks** | operator solves it; agents never solve CAPTCHAs. If the site blocks automated browsers entirely, use the fallback recorder (`scripts/fallback/`) in the operator's own Chrome |
| **Several accounts / roles** | one profile per account (`acme-admin`, `acme-member`); never switch users inside one profile mid-course |
| **Workspace / sub-account switching** | do it in the take's `setup()` (not recorded) by URL when possible (`go('/workspace/123/dashboard')`) |
| **Session expired** (a take lands on the sign-in page, or `status` shows it) | stop; run `login` again and hand over to the operator |
| **"New device" / security emails** | expected on the first login in a new profile; the operator confirms them |
| **Remote / cloud agent** (browser runs on a server) | the operator needs to *see* that browser to sign in: run it on a virtual display and connect with VNC/noVNC, sign in there, then disconnect. Don't copy cookies between machines |

## 4. Preparing the account for recording (do this with the operator, before the first take)
- **Demo workspace + demo user** with only the permissions the course needs; fake company, contacts, prices.
- Turn off things that pop up mid-take: product tours, "what's new" modals, chat widgets if possible, desktop
  notifications, cookie banners (accept/decline once in the recording profile).
- Set the display name/avatar to something neutral (it often appears in greetings and corners), or plan to blur it.
- Note anything on screen that's real (the operator's email in a menu, billing details) and keep takes away from it.

## 5. Security rules
- Profiles live in `$TRAINING_VIDEO_HOME/pw-<profile>/` (default `~/.training-video/`, created with owner-only
  permissions). They contain live sessions: never copy them into a project, a repo, a ticket or a cloud sandbox.
- Never commit `.env` files, cookies, HAR files, or screenshots of sign-in/billing pages. The `.gitignore` covers the usual ones.
- Never put tokens or session URLs in narration, file names, or the course tracker.
- Login and setup steps are **not recorded** (`setup()` and `login` run outside the take), so credentials never reach footage.
- If the operator has to show something sensitive to proceed, pause, let them do it, and re-shoot from a clean state.
