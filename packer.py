import struct

def hexdump(data):
    """Pretty print a hex dump of data, similar to xxd"""
    lines = []
    offset = 0
    while offset < len(data):
        piece = data[offset:offset + 16]
        bytes = ''.join([('%02x ' % ord(x)) for x in piece])
        chars = ''.join([(x if 0x20 < ord(x) < 0x7f else '.') for x in piece])
        lines.append('%04x  %-24s %-24s %-16s' % (offset, bytes[:24], bytes[24:], chars))
        offset += len(piece)
    return "\n".join(lines)


class Packer:
    """Helper class to nicely pack binary data on-the-go"""
    
    def __init__(self, endianness="be", bad_chars=None):
        if endianness == 'be':
            self.endian = '>'
        elif endianness == 'le':
            self.endian = '<'
        else:
            raise ValueError('Incorrect endianness argument')
        self.format_word = self.endian + 'I'
        self.code = ''
        self.bad_chars = bad_chars if bad_chars is not None else []
    def add(self, data):
        self.code += data
    def add_regmark(self, reg):
        self.add(reg.upper() * 2)
    def add_padding(self, length, char='A'):
        self.add(char * length)
    def add_word(self, word):
        self.add(struct.pack(self.format_word, word))
    def add_address(self, offset, base):
        self.add_word(base + offset)
    def verify(self):
        clean = True
        for bc in self.bad_chars:
            idx = self.code.find(bc)
            if idx != -1:
                print 'WARN: bad char %02x found at offset %d' % (ord(bc), idx)
                clean = False
        return clean
    def generate_chex(self):
        code = self.code
        parts = []
        offset = 0
        while len(code) > 0:
            l = ['"']
            l.extend(["\\x%02x" % ord(ch) for ch in code[:16]])
            l.append('" # %04x' % offset)
            offset += min(len(code), 16)
            parts.append(''.join(l))
            code = code[16:]
        return "\r\n".join(parts)

