"Provides functions to decode a NAR"
import construct
import struct

example = b'\r\x00\x00\x00\x00\x00\x00\x00nix-archive-1\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00(\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00type\x00\x00\x00\x00\x07\x00\x00\x00\x00\x00\x00\x00regular\x00\x08\x00\x00\x00\x00\x00\x00\x00contentsO\x00\x00\x00\x00\x00\x00\x00with (import <nixpkgs>) {};\nrunCommand "foo" {}\n\'\'\necho hi\necho boop > $out\n\'\'\n\x00\x01\x00\x00\x00\x00\x00\x00\x00)\x00\x00\x00\x00\x00\x00\x00'

nixstr = construct.Aligned(8, construct.PascalString(construct.Int64ul))

def fixed_nixstr(b):
    length = len(b)
    padding_length = (8 - (length % 8)) % 8
    padding = b'\0' * padding_length
    return struct.pack('Q', length) + b + padding

regular = construct.Struct(
    construct.Embedded(construct.Optional(construct.Struct(
        "flag" / construct.Const(nixstr, b"executable"),
        construct.Const(nixstr, b"")
    ))),
    construct.Const(fixed_nixstr(b"contents")),
    "contents" / nixstr
)

symlink = construct.Struct(
    construct.Const(fixed_nixstr(b"target")),
    "target" / nixstr
)

entry = construct.Struct(
    construct.Const(fixed_nixstr(b"entry")),
    construct.Const(fixed_nixstr(b"(")),
    construct.Const(fixed_nixstr(b"name")),
    "name" / nixstr,
    "node" / construct.LazyBound(lambda ctx: value),
    construct.Const(fixed_nixstr(b")"))
)

directory = construct.Struct(
    "entries" / construct.GreedyRange(entry)
)

value = construct.Struct(
    construct.Const(fixed_nixstr(b"(")),
    construct.Const(fixed_nixstr(b"type")),
    "type" / nixstr,
    construct.Embedded(construct.Switch(
        construct.this.type, {
            b"regular": regular,
            b"symlink": symlink,
            b"directory": directory,
        }
    )),
    construct.Const(fixed_nixstr(b")"))
)

dump = construct.Struct(
    construct.Const(fixed_nixstr(b"nix-archive-1")),
    construct.Embedded(value)
)
