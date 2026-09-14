# Workiom Vibe Apps

*Installed as `workiom-plugin`.*

Describe the internal page you need — a form, a tracker, a small tool — and get
a working app inside your Workiom workspace, reading and writing your real
lists.

This plugin bundles two things that only work together:

- the **`workiom-vibe-apps` skill**, which discovers your live schema, asks what
  the app should do, generates it, validates it, and publishes it
- the **Workiom connector**, which is how it reads your lists and publishes

## Install

From Workiom's marketplace:

```
/plugin marketplace add workiom/workiom-claude-plugins
/plugin install workiom-vibe-apps@workiom
```

A listing in the Claude community directory is pending review. Once it lands,
`/plugin install workiom-plugin@claude-community` works without adding a
marketplace first.

Installing the plugin brings both parts. Sign in to the Workiom connector with
your Workiom account the first time you use it.

Vibe apps are a private beta. If the assistant tells you the feature isn't
active for your workspace, contact support to have it switched on.

## Use

Just ask:

> "I need a page where support can log issues into our Bugs list."

It reads the list's real fields, checks what you want the app to do and how it
should look, builds it, and publishes it. You get a URL:

```
{tenant}.workiom.com/vibe/{appId}/
```

Anyone logged into that workspace can open it. The app acts as whoever is
viewing it — it has no credentials of its own and no access beyond theirs. If
a session expires, the viewer is sent to sign in and returned to the page.

Changes work the same way: *"add a priority dropdown"* fetches the app's real
source, edits it, and publishes a new version. Ask to go back and it
republishes the previous one.

## What it will not do

- Reach any origin other than Workiom's API — no CDNs, no external fonts or
  analytics
- Read, display, or log your session token
- Change your schema, roles, or permissions — a vibe app uses a list, it never
  reshapes one
- Publish an app that fails validation

## Limits

- Deleting a vibe app isn't available yet — an app can be disabled instead
- File-upload fields aren't supported inside an app; attach files in the main
  Workiom UI
- Bundles stay within the usual caps: ≤200 files, ≤5 MiB per file, and ≤4 MiB
  for the bundle as a whole — single-page or multi-page, whichever the app
  needs

## Trying something out

Ask for it to stay a draft. An app can be created without being published, so
it doesn't appear in the workspace until you've seen it and said go — useful
when you're still deciding what you want.

## What's in the box

```
.claude-plugin/plugin.json      plugin manifest
.mcp.json                       the Workiom connector this plugin ships with
skills/workiom-vibe-apps/
├── SKILL.md                    the pipeline the assistant follows
└── scripts/vibe-pack.py        bundle validator + packer
```

## Support

Issues and questions: <https://workiom.com>

## License

MIT — see [LICENSE](LICENSE).
