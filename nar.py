"Provides functions to decode a NAR"
import construct

example = b'\r\x00\x00\x00\x00\x00\x00\x00nix-archive-1\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00(\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00type\x00\x00\x00\x00\x07\x00\x00\x00\x00\x00\x00\x00regular\x00\x08\x00\x00\x00\x00\x00\x00\x00contentsO\x00\x00\x00\x00\x00\x00\x00with (import <nixpkgs>) {};\nrunCommand "foo" {}\n\'\'\necho hi\necho boop > $out\n\'\'\n\x00\x01\x00\x00\x00\x00\x00\x00\x00)\x00\x00\x00\x00\x00\x00\x00'

nixstr = construct.Aligned(8, construct.PascalString(construct.Int64ul))

regular = construct.Struct(
    construct.Const(nixstr, b"type"),
    "type" / construct.Const(nixstr, b"regular"),
    construct.Const(nixstr, b"contents"),
    "contents" / nixstr
)

executable = construct.Struct(
    construct.Const(nixstr, b"type"),
    construct.Const(nixstr, b"regular"),
    "type" / construct.Const(nixstr, b"executable"),
    construct.Const(nixstr, b""),
    construct.Const(nixstr, b"contents"),
    "contents" / nixstr
)

symlink = construct.Struct(
    construct.Const(nixstr, b"type"),
    "type" / construct.Const(nixstr, b"symlink"),
    construct.Const(nixstr, b"target"),
    "target" / nixstr
)

entry = construct.Struct(
    construct.Const(nixstr, b"entry"),
    construct.Const(nixstr, b"("),
    construct.Const(nixstr, b"name"),
    "name" / nixstr,
    "node" / construct.LazyBound(lambda ctx: value),
    construct.Const(nixstr, b")")
)

directory = construct.Struct(
    construct.Const(nixstr, b"type"),
    "type" / construct.Const(nixstr, b"directory"),
    "entries" / construct.GreedyRange(entry)
)

value = construct.Struct(
    construct.Const(nixstr, b"("),
    construct.Embedded(construct.Select(regular, executable, symlink, directory)),
    construct.Const(nixstr, b")")
)

dump = construct.Struct(
    construct.Const(nixstr, b"nix-archive-1"),
    construct.Embedded(value)
)
