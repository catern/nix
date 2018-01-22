import construct

def parse_with_con(con, bytes):
    fullcon = construct.Struct(
        "offset1"/construct.Tell,
        "value"/con,
        "offset2"/construct.Tell
    )
    try:
        parsed = fullcon.parse(bytes)
    # I *think* this corresponds exactly and only to errors where we
    # don't have enough bytes, but I'm not sure. Catching all
    # exceptions makes debugging parse errors nearly impossible, so I
    # don't really have an alternative.
    except construct.core.FieldError:
        return None, 0
    size = parsed["offset2"] - parsed["offset1"]
    return parsed["value"], size

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
