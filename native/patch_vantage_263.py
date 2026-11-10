#!/usr/bin/env python3
"""Compatibility-only patch against Vantage v0.15.1 (MIT).

Upstream issue #103: Minecraft 26.3 NBT block-state palettes switched from
Name/Properties compounds to id/properties compounds and compact string ids, including empty-key compounds.
We reuse every upstream subsystem and change only the native palette decoder.
The upstream checkout must be pinned to commit
953f0ac78d62de751a935b8e8d5be2d711d6fd56.
"""
from __future__ import annotations

import argparse
from pathlib import Path

OLD = """        for (palette, names, states) |p, *nm, *st| {
            nm.* = "minecraft:air";
            st.* = "";
            if (p == .compound) {
                if (nbt.get(p.compound, "Name")) |n| {
                    if (n.* == .string) nm.* = n.string;
                }
                if (nbt.get(p.compound, "Properties")) |pr| {
                    if (pr.* == .compound) st.* = try buildStateKey(arena, pr.compound);
                }
            }
        }
"""

NEW = """        for (palette, names, states) |p, *nm, *st| {
            // 26.3 accepts a bare block ID for default states, and lower-case
            // id/properties fields. Older worlds retain Name/Properties.
            st.* = "";
            switch (p) {
                .string => |id| nm.* = id,
                .compound => |entries| {
                    const id = nbt.get(entries, "id") orelse
                        nbt.get(entries, "Name") orelse
                        nbt.get(entries, "") orelse return error.BadFormat;
                    if (id.* != .string) return error.BadFormat;
                    nm.* = id.string;
                    if (nbt.get(entries, "properties") orelse
                        nbt.get(entries, "Properties")) |props| {
                        if (props.* != .compound) return error.BadFormat;
                        st.* = try buildStateKey(arena, props.compound);
                    }
                },
                // Unknown shapes must never silently become air.
                else => return error.BadFormat,
            }
        }
"""

TESTS = """
test "Minecraft 26.3 compact and renamed palette entries preserve actual blocks" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    var old_properties = [_]nbt.Entry{
        .{ .name = "axis", .tag = .{ .string = "x" } },
    };
    var new_properties = [_]nbt.Entry{
        .{ .name = "axis", .tag = .{ .string = "z" } },
    };
    var old_block = [_]nbt.Entry{
        .{ .name = "Name", .tag = .{ .string = "minecraft:oak_log" } },
        .{ .name = "Properties", .tag = .{ .compound = &old_properties } },
    };
    var new_block = [_]nbt.Entry{
        .{ .name = "id", .tag = .{ .string = "minecraft:oak_log" } },
        .{ .name = "properties", .tag = .{ .compound = &new_properties } },
    };
    var empty_key_block = [_]nbt.Entry{
        .{ .name = "", .tag = .{ .string = "minecraft:grass_block" } },
    };
    var empty_key_palette = [_]nbt.Tag{.{ .compound = &empty_key_block }};
    var old_palette = [_]nbt.Tag{.{ .compound = &old_block }};
    var new_palette = [_]nbt.Tag{.{ .compound = &new_block }};
    var string_palette = [_]nbt.Tag{.{ .string = "minecraft:stone" }};
    var old_bs = [_]nbt.Entry{.{ .name = "palette", .tag = .{
        .list = .{ .elem = .compound, .items = &old_palette },
    } }};
    var new_bs = [_]nbt.Entry{.{ .name = "palette", .tag = .{
        .list = .{ .elem = .compound, .items = &new_palette },
    } }};
    var empty_key_bs = [_]nbt.Entry{.{ .name = "palette", .tag = .{
        .list = .{ .elem = .compound, .items = &empty_key_palette },
    } }};
    var string_bs = [_]nbt.Entry{.{ .name = "palette", .tag = .{
        .list = .{ .elem = .string, .items = &string_palette },
    } }};
    var old_section = [_]nbt.Entry{
        .{ .name = "Y", .tag = .{ .byte = 0 } },
        .{ .name = "block_states", .tag = .{ .compound = &old_bs } },
    };
    var new_section = [_]nbt.Entry{
        .{ .name = "Y", .tag = .{ .byte = 1 } },
        .{ .name = "block_states", .tag = .{ .compound = &new_bs } },
    };
    var string_section = [_]nbt.Entry{
        .{ .name = "Y", .tag = .{ .byte = 2 } },
        .{ .name = "block_states", .tag = .{ .compound = &string_bs } },
    };
    var empty_key_section = [_]nbt.Entry{
        .{ .name = "Y", .tag = .{ .byte = 3 } },
        .{ .name = "block_states", .tag = .{ .compound = &empty_key_bs } },
    };
    var sections = [_]nbt.Tag{
        .{ .compound = &old_section },
        .{ .compound = &new_section },
        .{ .compound = &string_section },
        .{ .compound = &empty_key_section },
    };
    var root = [_]nbt.Entry{
        .{ .name = "DataVersion", .tag = .{ .int = 5023 } },
        .{ .name = "xPos", .tag = .{ .int = 0 } },
        .{ .name = "zPos", .tag = .{ .int = 0 } },
        .{ .name = "sections", .tag = .{
            .list = .{ .elem = .compound, .items = &sections },
        } },
    };
    const decoded = try decode(a, &root);
    try std.testing.expectEqual(@as(usize, 4), decoded.sections.len);
    try std.testing.expectEqualStrings("minecraft:oak_log", decoded.sections[0].names[0]);
    try std.testing.expectEqualStrings("axis=x", decoded.sections[0].states[0]);
    try std.testing.expectEqualStrings("minecraft:oak_log", decoded.sections[1].names[0]);
    try std.testing.expectEqualStrings("axis=z", decoded.sections[1].states[0]);
    try std.testing.expectEqualStrings("minecraft:stone", decoded.sections[2].names[0]);
    try std.testing.expectEqualStrings("", decoded.sections[2].states[0]);
    try std.testing.expectEqualStrings("minecraft:grass_block", decoded.sections[3].names[0]);
}
"""


def apply_patch(source: str) -> str:
    if source.count(OLD) != 1:
        raise ValueError("Vantage 0.15.1 palette decoder does not match pinned patch; refusing to modify")
    if 'test "Minecraft 26.3 compact and renamed palette entries' in source:
        raise ValueError("Vantage 26.3 patch already applied")
    return source.replace(OLD, NEW) + "\n" + TESTS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path, help="Pinned Vantage source checkout")
    args = parser.parse_args()
    file = args.upstream / "src" / "chunk.zig"
    original = file.read_text(encoding="utf-8")
    modified = apply_patch(original)
    file.write_text(modified, encoding="utf-8")
    print("Applied minimal 26.3 palette compatibility fix to pinned Vantage source")


if __name__ == "__main__":
    main()
