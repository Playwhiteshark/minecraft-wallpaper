# Minecraft Living World Wallpaper

A **proposed**, lightweight, self-updating cinematic desktop representation of a real Minecraft Java world.

The goal is to turn selected areas of a saved Minecraft world into an atmospheric Lively Wallpaper scene with subtle **3D parallax**, adaptable framing, meaningful resident mobs, and optional video fallback—**without keeping Minecraft, its simulation, or a full shader pipeline running**.

> **Status: research and product definition only. No wallpaper engine, extractor, scheduled job or Minecraft mod has been implemented or installed.**

## Read first

- [Product specification](docs/PRODUCT-SPEC.md) — goal, user experience, scope, constraints, success criteria, architecture and pending decisions.
- [Existing software and technology research](docs/RESEARCH.md) — BlueMap, Vantage, Worldlens, pet/entity rendering, Lively, game-as-wallpaper mods, trade-offs and feasibility questions.
- [Feasibility issue #1](https://github.com/Playwhiteshark/minecraft-wallpaper/issues/1) — experiments and decisions needed before implementation.

## Core distinction

This is **not** an always-running Minecraft window on the desktop, or a general-purpose map of an entire world. It aims for a beautiful, base-size-aware, pet-aware, POI-aware **desktop diorama** extracted from an authentic save. Existing world-to-3D tooling should be reused rather than rewritten without evidence.

## Repository ownership

This is an **independent standalone application** and owns its product design, research, future source, integration contracts and issue tracker. Local Windows Tools is not its application host or replaceable runtime; it may eventually provide a narrow, on-demand launcher/status integration. Lively Wallpaper is the existing wallpaper host.

Do **not** commit personal world saves, absolute machine paths, coordinates of private POIs, sensitive world/server details, tokens or generated image/video artifacts. Local user configuration, entity identifiers and source worlds belong outside the product source checkout.

[Background: original planning issue in private personal-ops](https://github.com/Playwhiteshark/personal-ops/issues/49), to be replaced by a migration pointer once transferred.
