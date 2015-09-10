"""
A tool for ZyNOS firmware update binaries.

References:
https://dev.openwrt.org/browser/trunk/tools/firmware-utils/src/zynos.h

"""

import sys
import struct

class RomIoHeader(struct.Struct):
    def __init__(self, source=None):
        struct.Struct.__init__(self, '>Ixx3sBIIBxHH15sIxxxxx')
        if source is not None:
            self.unpack(source)
        else:
            self.load_addr = 0L
            self.signature = 'SIG'
            self.type = 0
            self.orig_size = 0
            self.orig_checksum = 0
            self.comp_size = 0
            self.comp_checksum = 0
            self.flags = 0
            self.version = "\0" * 15
            self.mmap_addr = 0L
    def __str__(self):
        lines = []
        lines.append("  Type: %02X"% self.type)
        lines.append("  Loading address: %08X" % self.load_addr)
        lines.append("  Memmap address: %08X" % self.mmap_addr)
        lines.append("  Flags: %02X" % self.flags)
        if self.flags & 0x40:
            lines.append("  Original size: %08X; checksum: %04X" % (self.orig_size, self.orig_checksum))
        else:
            lines.append("  Original size: %08X" % self.orig_size)
        if self.flags & 0x80:
            if self.flags & 0x20:
                lines.append("  Compressed size: %08X; checksum: %04X" % (self.comp_size, self.comp_checksum))
            else:
                lines.append("  Compressed size: %08X" % self.comp_size)
        return "\n".join(lines)
    def pack(self):
        return struct.Struct.pack(
            self,
            self.load_addr,
            self.signature,
            self.type,
            self.orig_size, self.comp_size,
            self.flags,
            self.orig_checksum, self.comp_checksum,
            self.version,
            self.mmap_addr)
    def unpack(self, source):
        self.load_addr, self.signature, self.type, self.orig_size, self.comp_size, self.flags, self.orig_checksum, self.comp_checksum, self.version, self.mmap_addr = struct.Struct.unpack(self, source)
#
class MemoryMapHeader(struct.Struct):
    def __init__(self, source=None):
        struct.Struct.__init__(self, '>HIIH12x')
        if source is not None:
            self.unpack(source)
        else:
            self.count = 0
            self.user_start = 0L
            self.user_end = 0L
            self.checksum = 0
    def __str__(self):
        return "%d entries (USER: %08X..%08X)" % (self.count, self.user_start, self.user_end)
    def pack(self):
        return struct.Struct.pack(self, self.count, self.user_start, self.user_end, self.checksum)
    def unpack(self, source):
        self.count, self.user_start, self.user_end, self.checksum = struct.Struct.unpack(self, source)
#
class MemoryMapEntry(struct.Struct):
    def __init__(self, source=None):
        struct.Struct.__init__(self, '>B8sxIxxII')
        if source is not None:
            self.unpack(source)
        else:
            self.type1 = 0
            self.type2 = 0
            self.name = ''
            self.address = 0L
            self.length = 0L
    def __str__(self):
        return "%08X %08X %s (%d, %d)" % (self.address, self.length, self.name, self.type1, self.type2)
    def pack(self):
        return struct.Struct.pack(self, self.type1, self.name, self.address, self.length, self.type2)
    def unpack(self, source):
        self.type1, self.name, self.address, self.length, self.type2 = struct.Struct.unpack(self, source)
#
class CheckSum(object):
    def __init__(self):
        self.sum = 0
        self.__last = None
    def update(self, data):
        if self.__last is not None:
            data = self.__last + data
            self.__last = None
        offset = 0
        l = (len(data) // 2) * 2
        s = struct.Struct('>H')
        while offset < l:
            self.sum += s.unpack_from(data, offset)
            if self.sum > 0xFFFF:
                self.sum = (1 + self.sum) & 0xFFFF
            offset += 2
        if offset < len(data):
            self.__last = data[-1]
    def get(self):
        self.update("\0")
        return self.sum

fp = open(sys.argv[1], 'rb')

print("Reading the RAS image ROMIO header")
romio_header = RomIoHeader(fp.read(48))
print("Header dump:")
print(str(romio_header))

print("Searching for the memory map table")
offset = 0x100
while True:
    fp.seek(offset)
    mmh = MemoryMapHeader(fp.read(24))
    if mmh.user_start - (mmh.count + 1) * 24 == romio_header.mmap_addr:
        print("Memory map table found at offset %X in the file" % offset)
        break
    offset += 0x100
mmt = []
while len(mmt) < mmh.count:
    e = MemoryMapEntry(fp.read(24))
    mmt.append(e)
    print str(e)
