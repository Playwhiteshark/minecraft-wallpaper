#!/usr/bin/env python3
"""Tiny optional surface-only geometry policy on top of pinned Vantage 0.15.1.

Reuses Vantage's chunk reader, block model resolver, light pass, greedy mesher,
tile cache and embedded Three.js viewer. Nothing is changed in the source world.

--surface-depth N keeps exposed faces for surface blocks and a N-block-deep
skirt per X/Z column, respecting lower neighbouring terrain so visible cliffs
remain intact. Below-cut blocks still participate in occlusion and lighting;
they simply do not emit render geometry. No fake bottom faces or heightfield.
The default upstream behavior remains unchanged when the flag is omitted.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Unexpected upstream {label} shape ({count} matches); refusing patch")
    return source.replace(old, new)


def patch_mesh(source: str) -> str:
    source = replace_once(source, """    max_threads: usize,
    progress: ?std.Progress.Node,
) !Built {""",
"""    max_threads: usize,
    surface_depth: ?u16,
    progress: ?std.Progress.Node,
) !Built {""", "mesh signature")
    source = replace_once(source, """        .interior = interior orelse grid.Interior.full(g),
        .cave_y = switch (cave) {""",
"""        .interior = interior orelse grid.Interior.full(g),
        .surface_floor = if (surface_depth) |depth| try surfaceFloors(arena, g, depth) else &.{},
        .cave_y = switch (cave) {""", "mesh context construction")
    source = replace_once(source, """    interior: grid.Interior,
    /// Cave culling:""",
"""    interior: grid.Interior,
    /// N-block surface skirt, with local cliff floors lowered to adjacent real
    /// terrain heights. No geometry emitted below floor, but the original block
    /// grid remains intact for lighting and occlusion. Empty means full-depth.
    surface_floor: []const usize = &.{},

    fn surfaceVisible(ctx: *const MeshCtx, x: usize, y: usize, z: usize) bool {
        return ctx.surface_floor.len == 0 or
            y >= ctx.surface_floor[z * ctx.g.sx + x];
    }
    /// Cave culling:""", "mesh context surface boundary")
    # Per-block faces and water/lava side walls.
    source = replace_once(source, """                const id = g.ids[g.index(x, y, z)];
                if (id == grid.AIR) continue;
                // Pure terrain blocks""",
"""                const id = g.ids[g.index(x, y, z)];
                if (id == grid.AIR or !ctx.surfaceVisible(x, y, z)) continue;
                // Pure terrain blocks""", "per-block surface predicate")
    # Greedy faces (terrain stone/dirt/grass, including all long exposed walls).
    source = replace_once(source, """                const id = g.ids[gi];
                if (id == grid.AIR) continue;
                const gf = ctx.greedy_faces[id];""",
"""                const id = g.ids[gi];
                if (id == grid.AIR or !ctx.surfaceVisible(x, y, z)) continue;
                const gf = ctx.greedy_faces[id];""", "greedy surface predicate")
    # Greedy water and lava tops (shared with the same column mask).
    source = replace_once(source, """            const id = g.ids[g.index(x, y, z)];
            if (id == grid.AIR) continue;
            if (kind == .water) {""",
"""            const id = g.ids[g.index(x, y, z)];
            if (id == grid.AIR or !ctx.surfaceVisible(x, y, z)) continue;
            if (kind == .water) {""", "fluid surface predicate")
    anchor = "/// Immutable, shareable context for the per-cell mesh pass (read by every thread)."
    function = """/// Compute a continuous, *geometry-only* surface ribbon for an actual 3D
/// Minecraft block grid. Each column begins at its highest real block; a
/// neighbour that is genuinely lower extends the wall budget downward to meet
/// the lower ground. The one-chunk apron supplies actual adjacent heights at
/// tile boundaries, so this policy never invents geometry to fill a gap.
/// Empty neighbours are deliberately ignored, not interpreted as bedrock.
fn surfaceFloors(a: std.mem.Allocator, g: grid.Grid, depth: u16) ![]usize {
    const n = g.sx * g.sz;
    const top = try a.alloc(usize, n);
    const raw = try a.alloc(usize, n);
    const out = try a.alloc(usize, n);
    const d: usize = @intCast(depth);
    for (0..g.sz) |z| {
        for (0..g.sx) |x| {
            const i = z * g.sx + x;
            var y = g.sy;
            while (y > 0) {
                y -= 1;
                if (g.ids[g.index(x, y, z)] != grid.AIR) break;
            }
            if (g.ids[g.index(x, y, z)] == grid.AIR) {
                top[i] = g.sy;
                raw[i] = g.sy;
            } else {
                top[i] = y;
                raw[i] = (y + 1) -| d;
            }
        }
    }
    for (0..g.sz) |z| for (0..g.sx) |x| {
        const i = z * g.sx + x;
        var floor = raw[i];
        if (top[i] != g.sy) {
            if (x > 0 and top[i - 1] != g.sy) floor = @min(floor, raw[i - 1]);
            if (x + 1 < g.sx and top[i + 1] != g.sy) floor = @min(floor, raw[i + 1]);
            if (z > 0 and top[i - g.sx] != g.sy) floor = @min(floor, raw[i - g.sx]);
            if (z + 1 < g.sz and top[i + g.sx] != g.sy) floor = @min(floor, raw[i + g.sx]);
        }
        out[i] = floor;
    };
    return out;
}

test "surface ribbon excludes deep exposed walls without creating bottom geometry" {
    const a = std.testing.allocator;
    var ids = [_]u16{1} ** (2 * 1 * 64);
    // Two genuine adjacent columns: one 64-block cliff, one 16-block ground.
    for (48..64) |y| ids[y * 2 + 1] = grid.AIR;
    var names = [_][]const u8{ "", "minecraft:stone" };
    const g: grid.Grid = .{
        .sx = 2, .sy = 64, .sz = 1,
        .min_x = 0, .min_y = 0, .min_z = 0,
        .ids = &ids, .names = &names,
    };
    const floors = try surfaceFloors(a, g, 8);
    defer a.free(floors);
    // High cliff retains sides down to the real adjacent lower terrain + skirt.
    try std.testing.expectEqual(@as(usize, 40), floors[0]);
    try std.testing.expectEqual(@as(usize, 40), floors[1]);
    // No deep walls when the next column is missing/unpopulated.
    @memset(ids[0..], 0);
    for (0..64) |y| ids[y * 2] = 1;
    const isolated = try surfaceFloors(a, g, 8);
    defer a.free(isolated);
    try std.testing.expectEqual(@as(usize, 56), isolated[0]);
    try std.testing.expectEqual(@as(usize, 64), isolated[1]);
}

"""
    source = replace_once(source, anchor, function + anchor, "surface function")
    return source


def patch_main(source: str) -> str:
    start = source.index("fn runLiveMode(")
    head, live = source[:start], source[start:]
    # The optional flag is scoped to native live streaming; offline exports are
    # not unexpectedly changed. The user's app explicitly requests it.
    parser = """fn parseSurfaceDepth(args: []const []const u8) !?u16 {
    var i: usize = 0;
    while (i + 1 < args.len) : (i += 1) {
        if (!std.mem.eql(u8, args[i], "--surface-depth")) continue;
        const value = args[i + 1];
        const n = std.fmt.parseInt(u16, value, 10) catch
            return badValue("--surface-depth", value, "1..64 blocks");
        if (n < 1 or n > 64) return badValue("--surface-depth", value, "1..64 blocks");
        return n;
    }
    return null;
}

"""
    head += parser
    live = replace_once(live,
        "    const requested_caves = try parseCaveY(args);\n    const ceiling = try parseCeiling(args);",
        "    const requested_caves = try parseCaveY(args);\n    const surface_depth = try parseSurfaceDepth(args);\n    const ceiling = try parseCeiling(args);",
        "live flag parsing")
    live = replace_once(live,
        'std.mem.eql(u8, arg, "--caves") or std.mem.eql(u8, arg, "--threads") or',
        'std.mem.eql(u8, arg, "--caves") or std.mem.eql(u8, arg, "--surface-depth") or\n            std.mem.eql(u8, arg, "--threads") or',
        "live flag consumption")
    live = replace_once(live,
        "        .cave_y = cave_y,\n        .gz_level = gz_level,",
        "        .cave_y = cave_y,\n        .surface_depth = surface_depth,\n        .gz_level = gz_level,",
        "live shared config")
    source = head + live
    source = replace_once(source, "    cave_y: ?i32,\n    gz_level: i32,\n    /// Batch-only",
                          "    cave_y: ?i32,\n    surface_depth: ?u16 = null,\n    gz_level: i32,\n    /// Batch-only", "Shared surface mode")
    source = replace_once(source, "    cave_y: ?i32,\n    gz_level: i32,\n    mesh_threads: usize,",
                          "    cave_y: ?i32,\n    surface_depth: ?u16 = null,\n    gz_level: i32,\n    mesh_threads: usize,", "SharedConfig surface mode")
    source = replace_once(source,
        "        .cave_y = cfg.cave_y,\n        .gz_level = cfg.gz_level,",
        "        .cave_y = cfg.cave_y,\n        .surface_depth = cfg.surface_depth,\n        .gz_level = cfg.gz_level,",
        "Shared construction")
    source = replace_once(source,
        "sh.caveMode(), sh.mesh_threads, null);",
        "sh.caveMode(), sh.mesh_threads, sh.surface_depth, null);",
        "native tile build")
    source = replace_once(source,
        " }, 0, null);\n    const arr = try builder.finish();",
        " }, 0, null, null);\n    const arr = try builder.finish();",
        "single tile build")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path, help="Pinned Vantage source checkout, already palette-patched")
    args = parser.parse_args()
    src = args.upstream / "src"
    mesh_file, main_file = src / "mesh.zig", src / "main.zig"
    new_mesh = patch_mesh(mesh_file.read_text(encoding="utf-8"))
    new_main = patch_main(main_file.read_text(encoding="utf-8"))
    mesh_file.write_text(new_mesh, encoding="utf-8")
    main_file.write_text(new_main, encoding="utf-8")
    print("Patched Vantage live with optional geometry-only --surface-depth mode")


if __name__ == "__main__":
    main()
