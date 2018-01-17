"Provides functions to decode a NAR"
import construct

example = b'\r\x00\x00\x00\x00\x00\x00\x00nix-archive-1\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00(\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00type\x00\x00\x00\x00\x07\x00\x00\x00\x00\x00\x00\x00regular\x00\x08\x00\x00\x00\x00\x00\x00\x00contentsO\x00\x00\x00\x00\x00\x00\x00with (import <nixpkgs>) {};\nrunCommand "foo" {}\n\'\'\necho hi\necho boop > $out\n\'\'\n\x00\x01\x00\x00\x00\x00\x00\x00\x00)\x00\x00\x00\x00\x00\x00\x00'

nixstr = construct.Aligned(8, construct.PascalString(construct.Int64ul, encoding="utf8"))

regular = construct.Struct(
    construct.Const(nixstr, "type"),
    "type" / construct.Const(nixstr, "regular"),
    construct.Const(nixstr, "contents"),
    "contents" / nixstr
)

executable = construct.Struct(
    construct.Const(nixstr, "type"),
    construct.Const(nixstr, "regular"),
    "type" / construct.Const(nixstr, "executable"),
    construct.Const(nixstr, ""),
    construct.Const(nixstr, "contents"),
    "contents" / nixstr
)

symlink = construct.Struct(
    construct.Const(nixstr, "type"),
    "type" / construct.Const(nixstr, "symlink"),
    construct.Const(nixstr, "target"),
    "target" / nixstr
)

entry = construct.Struct(
    construct.Const(nixstr, "entry"),
    construct.Const(nixstr, "("),
    construct.Const(nixstr, "name"),
    "name" / nixstr,
    "node" / construct.LazyBound(lambda ctx: value),
    construct.Const(nixstr, ")")
)

directory = construct.Struct(
    construct.Const(nixstr, "type"),
    "type" / construct.Const(nixstr, "directory"),
    "entries" / construct.GreedyRange(entry)
)

value = construct.Struct(
    construct.Const(nixstr, "("),
    construct.Embedded(construct.Select(regular, executable, symlink, directory)),
    construct.Const(nixstr, ")")
)

dump = construct.Struct(
    construct.Const(nixstr, "nix-archive-1"),
    construct.Embedded(value)
)
