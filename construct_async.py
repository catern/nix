import construct

def parse_with_con(con, bytes):
    parsed = construct.Optional(construct.Struct(
        "offset1"/construct.Tell,
        "value"/con,
        "offset2"/construct.Tell
    )).parse(bytes)
    if parsed is not None:
        size = parsed["offset2"] - parsed["offset1"]
        return parsed["value"], size
    else:
        return None, 0

class DataPoller:
    def __init__(self, read):
        self._read = read
        self.buf = bytes()

    async def wait_for_more(self):
        self.buf += await self._read()

    def available(self):
        return self.buf

    def consume(self, n):
        self.buf = self.buf[n:]

def con_reader(read):
    reader = DataPoller(read)
    async def read_con(con):
        while True:
            value, consumed = parse_with_con(con, reader.available())
            if value is not None:
                reader.consume(consumed)
                return value
            await reader.wait_for_more()
    return read_con

def con_writer(write):
    async def write_con(con, data):
        built = con.build(data)
        await write(built)
    return write_con
