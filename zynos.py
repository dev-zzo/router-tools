"""
A tool for ZyNOS firmware update binaries.

References:
https://dev.openwrt.org/browser/trunk/tools/firmware-utils/src/zynos.h

A few notes on unpacked data.

Sections that start with ROMIO header (the one with SIG) and compressed with LZMA
start with 3 byte offset after the header. No idea what was supposed to go there.

"""

import sys
import struct

class RomIoHeader(struct.Struct):
    SIGNATURE = 'SIG'

    def __init__(self, source=None):
        struct.Struct.__init__(self, '>Ixx3sBIIBxHH15sIxxxxx')
        if source is not None:
            self.unpack(source)
        else:
            self.load_addr = 0L
            self.signature = RomIoHeader.SIGNATURE
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
        return "%d entries (USER: %08X..%08X), checksum %04X" % (self.count, self.user_start, self.user_end, self.checksum)
    def pack(self):
        return struct.Struct.pack(self, self.count, self.user_start, self.user_end, self.checksum)
    def unpack(self, source):
        self.count, self.user_start, self.user_end, self.checksum = struct.Struct.unpack(self, source)
#
class MemoryMapEntry(struct.Struct):
    Type1Names = {
        0x01: 'ROMIMG',
        0x02: 'ROMBOOT',
        0x03: 'BOOTEXT',
        0x04: 'ROMBIN',
        0x05: 'ROMDIR',
        0x07: 'ROMMAP',
        0x81: 'RAMCODE',
        0x82: 'RAMBOOT',
    }

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
        try:
            type_name = MemoryMapEntry.Type1Names[self.type1]
        except KeyError:
            type_name = str(self.type1)
        return "%08X %08X '%-8s' (%s, %d)" % (self.address, self.length, self.name, type_name, self.type2)
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
        while offset < l:
            self.sum += (ord(data[offset]) << 8) + ord(data[offset + 1])
            if self.sum > 0xFFFF:
                self.sum = (1 + self.sum) & 0xFFFF
            offset += 2
        if offset < len(data):
            self.__last = data[-1]
    def get(self):
        self.update("\0")
        return self.sum


def find_memory_map(fp, mmap_addr):
    fp.seek(0, 2)
    size = fp.tell()
    offset = 0x100
    mmh = MemoryMapHeader()
    while offset < size - 0x100:
        fp.seek(offset)
        mmh.unpack(fp.read(0x18))
        calculated_addr = mmh.user_start - (mmh.count + 1) * 0x18
        if calculated_addr == mmap_addr:
            mmt_length = mmh.user_end - mmap_addr - 0x18
            if 0 <= mmt_length < size - offset:
                csum = CheckSum()
                csum.update(fp.read(mmt_length))
                if csum.get() == mmh.checksum:
                    return offset
        offset += 0x100
    return None
#
def read_memory_map(fp, mmap_addr):
    mmh_offset = find_memory_map(fp, mmap_addr)
    if mmh_offset is None:
        return None
    fp.seek(mmh_offset)
    mmh = MemoryMapHeader(fp.read(0x18))
    mmt = []
    while len(mmt) < mmh.count:
        e = MemoryMapEntry(fp.read(0x18))
        e.name = e.name.rstrip("\0")
        mmt.append(e)
    return mmt
#
def do_info(ras_path):
    fp = open(ras_path, 'rb')

    print("Reading the RAS image ROMIO header.")
    romio_header = RomIoHeader(fp.read(0x30))
    if romio_header.signature != RomIoHeader.SIGNATURE:
        print("Incorrect header signature!")
        return
    print("Header dump:")
    print(str(romio_header))
    print('')

    mmt = read_memory_map(fp, romio_header.mmap_addr)
    if mmt is None:
        return
    print("Memory map:")
    for mme in mmt:
        print str(mme)
#
def do_unpack(ras_path):
    fp = open(ras_path, 'rb')
    romio_header = RomIoHeader(fp.read(0x30))
    mmt = read_memory_map(fp, romio_header.mmap_addr)
    if mmt is None:
        return

    bootext_base = None
    for mme in mmt:
        if mme.type1 == 1 and mme.name == 'BootExt':
            bootext_base = mme.address - 0x30
            break
    if bootext_base is None:
        print("No BootExt section -- can't figure out where the image is based")
        return

    print("Unpacking sections:")
    for mme in mmt:
        print str(mme)
        if mme.type1 & 0x80:
            #print("-> RAM section, dropping")
            continue
        offset = mme.address - bootext_base
        if offset < 0:
            #print("-> No data in image, dropping")
            continue
        fp.seek(offset)
        data_length = mme.length
        out_name = "%s.%s" % (ras_path, mme.name)
        if mme.name in ('HTPCode', 'RasCode'):
            sh = RomIoHeader(fp.read(0x30))
            if sh.signature == RomIoHeader.SIGNATURE:
                data_length = sh.comp_size
                out_name = "%s.%s.7z" % (ras_path, mme.name)
                fp.seek(3, 1)
            else:
                fp.seek(offset)
        out_fp = open(out_name, 'wb')
        data = fp.read(data_length)
        if len(data) != data_length:
            print("-> NOTE: not all data is in the image")
        out_fp.write(data)
        out_fp.close()
#

if __name__ == '__main__':
    print("ZyNOS firmware tool by dev_zzo, version 0")
    print('')
    do_unpack(sys.argv[1])
