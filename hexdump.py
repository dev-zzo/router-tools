"""
Simple dumper of data in hex.
"""

def __dump_bytes(data):
    return ' '.join([('%02X' % ord(x)) for x in data])
def __dump_chars(data):
    return ''.join([(x if 0x20 <= ord(x) <= 0x80 else '.') for x in data])
def dump(data):
    i = 0
    lines = []
    while i < len(data):
        line = data[i:(i + 16)]
        p1 = __dump_bytes(line[:8])
        p2 = __dump_bytes(line[8:]) if len(line) > 8 else ''
        lines.append('%08X  %-24s %-24s %s' % (i, p1, p2, __dump_chars(line)))
        i += 16
    return "\n".join(lines)
# EOF
