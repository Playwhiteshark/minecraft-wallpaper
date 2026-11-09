# Agent instructions — Minecraft Living World Wallpaper

This is an **independent standalone project**, not a submodule or tool of Local Windows Tools. Its canonical source, specifications, research and issue tracker belong **in this repository**.

## Required orientation

1. Read [README.md](README.md), [docs/PRODUCT-SPEC.md](docs/PRODUCT-SPEC.md) and [docs/RESEARCH.md](docs/RESEARCH.md).
2. Read the user-established Local Windows Tools governance in [desktop-tools/AGENTS.md](https://github.com/Playwhiteshark/desktop-tools/blob/main/AGENTS.md), [recording/routing](https://github.com/Playwhiteshark/desktop-tools/blob/main/docs/RECORDING-AND-ROUTING.md), [filesystem conventions](https://github.com/Playwhiteshark/desktop-tools/blob/main/docs/LOCAL-FILESYSTEM-CONVENTIONS.md) and [standalone-project contract](https://github.com/Playwhiteshark/desktop-tools/blob/main/docs/STANDALONE-PROJECTS.md) before altering packaging, automation or system integration.
3. Search source, documentation and issues before adding duplicate functionality or independent tooling.
4. Use `main` as the only canonical long-lived branch; temporary feature branches merge back into `main`.
5. Record durable architecture/behaviour in the appropriate existing docs and source, and unfinished tasks in issues—not chat transcripts.

## Design boundaries

- The actual Minecraft Java **world save is read-only user data**. Never commit it, modify it, or upload it. Take consistent snapshots and handle concurrent game saving safely.
- Never commit machine-specific Minecraft paths, private POI/world coordinates, entity UUIDs, server connection data, credentials or user generated wallpaper videos to this public repo.
- **Lively Wallpaper is the display host**; use documented integrations and preserve the user's independently maintained Lively Desktop Picture customization. Do not alter external DLLs or wallpaper settings without explicit action.
- Do not leave Minecraft running or implement a resident game-server/watcher to achieve the wallpaper. Rendering/extraction should occur only in bounded jobs; live wallpaper should use compact scene/video media and pause appropriately.
- Important resident mobs, scenic quality, small-base framing, POIs and selective updates are actual requirements—not optional details to discard to simplify implementation.
- Prefer existing tested renderers/converters; never start writing a complete new Minecraft world decoder without comparative evidence in the research document.
- No automatic system mutations, scheduled jobs, world hook/mod or app install while the project is still in proposal/feasibility state.

## Ownership and filesystem lifecycle

- Editable source: typically `%USERPROFILE%\CODING STUFF\minecraft-wallpaper`.
- Durable user-owned config and rendered output must be outside installed/replaced app runtime. Do not select a path until the implementation specifies its setup/migration/uninstall contract.
- All six external-write classes (logs, cache, runtime state, config, artifacts, user data) must be documented using `none`, `declared`, or `unknown`, following Desktop Tools conventions.
- Temporary files must have a bounded owned location and be cleaned on success, failure and cancellation. Never delete original worlds or unrelated files.
- Create/update docs alongside durable changes, verify actual compatibility/power budget on a real save and Lively build, and mark tests that weren't performed as unverified.

The original [personal-ops issue #49](https://github.com/Playwhiteshark/personal-ops/issues/49) is a migrated history pointer. New development and research belong here.
