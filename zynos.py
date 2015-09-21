"""
A tool for ZyNOS firmware update binaries.

References:
https://dev.openwrt.org/browser/trunk/tools/firmware-utils/src/zynos.h
http://www.ixo.de/info/zyxel_uclinux/

# What is actually in the firmware?

Every device contains an initial program loader called BootBase. The goal
of this software piece is to locate the next stage, load it, and pass control.

The next stage would typically be a second-stage loader called BootExt or
BootExtension; this one also provides for minimal debugging capabilities
via serial console (where physically available). It also allows to load and
execute the next stage.

The next stage (of those that are stored on the device) is either RAS or HTP.
RAS (acronym?) would be the main firmware, the one you typically would want to run.
HTP is a Hardware Test Program, performing various tests depending on the board.

Now, how boot code knows where all the different parts are located?

There is a certain, very important structure called "memory map table",
shorted to "memMapTab" and available via the ATMP command of boot extension.
This table stores location of every object there is in memory, both ROM and RAM.
So dumping that one would be VERY useful in reverse engineering efforts.
Moreover, it allows to correctly tie the image to the memory location and
correctly extract all the objects.

# What is actually ZyNOS?

Nobody knows! It is being told that ZyNOS is ZyXEL Network Operating System,
but from I could tell by inspecting the images, at least some of them are based
off ThreadX.

Specifically, the following identifying strings were found:
- ThreadX R3900/Green Hills Version G3.0f.3.0b
    Billion BiPAC 5100, 5102, 5102S, 5200/SRC/SRD, 5210SRF
    D-LINK DSL-2640R, DSL-2641R, DSL-2740R
    TP-LINK TD-8816 V1 through V7
    ZTE ZXV10 W300
    ZyXEL P-2602HWL-D3A
    ZyXEL P-2602HW-61
    ZyXEL P-660HN-T3A, P-660HW-D1, P-660HW-T1
- ThreadX MIPS32_M14K/GNU Version G5.5.5.0 SN: 3461-183-0501
    TP-LINK TD-8816 V8

"""

import argparse
import os.path
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
            self.orig_length = 0
            self.orig_checksum = 0
            self.comp_length = 0
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
            lines.append("  Original size: %08X; checksum: %04X" % (self.orig_length, self.orig_checksum))
        else:
            lines.append("  Original size: %08X" % self.orig_length)
        if self.flags & 0x80:
            if self.flags & 0x20:
                lines.append("  Compressed size: %08X; checksum: %04X" % (self.comp_length, self.comp_checksum))
            else:
                lines.append("  Compressed size: %08X" % self.comp_length)
        return "\n".join(lines)
    def pack(self):
        return struct.Struct.pack(
            self,
            self.load_addr,
            self.signature,
            self.type,
            self.orig_length, self.comp_length,
            self.flags,
            self.orig_checksum, self.comp_checksum,
            self.version,
            self.mmap_addr)
    def unpack(self, source):
        self.load_addr, self.signature, self.type, self.orig_length, self.comp_length, self.flags, self.orig_checksum, self.comp_checksum, self.version, self.mmap_addr = struct.Struct.unpack(self, source)
        if self.signature != RomIoHeader.SIGNATURE:
            raise ValueError('signature mismatch')
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
        0x06: 'ROM68K',
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
        return "'%-8s' at %08X, size %08X (%s, %d)" % (self.name, self.address, self.length, type_name, self.type2)
    def pack(self):
        return struct.Struct.pack(self, self.type1, self.name, self.address, self.length, self.type2)
    def unpack(self, source):
        self.type1, self.name, self.address, self.length, self.type2 = struct.Struct.unpack(self, source)
#
def checksum(data):
    sum = 0
    offset = 0
    limit = (len(data) >> 1) << 1
    while offset < limit:
        sum += (ord(data[offset]) << 8) + ord(data[offset + 1])
        if sum > 0xFFFF:
            sum = (1 + sum) & 0xFFFF
        offset += 2
    if offset != len(data):
        sum += ord(data[-1]) << 8
        if sum > 0xFFFF:
            sum = (1 + sum) & 0xFFFF
    return sum
#
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
                if checksum(fp.read(mmt_length)) == mmh.checksum:
                    return offset
        offset += 0x100
    return None
#
def do_unpack(args):
    "Process the input image"

    print("Processing the RAS image from '%s'." % args.input_file)
    fp = open(args.input_file, 'rb')
    fp.seek(0, 2)
    image_size = fp.tell()
    fp.seek(0, 0)

    romio_header = RomIoHeader(fp.read(0x30))
    print("ZyNOS ROMIO header:")
    print(str(romio_header))
    
    if romio_header.flags & 0x40:
        print("Verifying image checksum...")
        this_checksum = checksum(fp.read(romio_header.orig_length))
        if this_checksum != romio_header.orig_checksum:
            print("Checksum verification failed: expected %04X, calculated %04X" % (romio_header.orig_checksum, this_checksum))
            return
    print('')

    print("Searching for memory map table...")
    mmh_offset = find_memory_map(fp, romio_header.mmap_addr)
    if mmh_offset is None:
        print("Memory map table not found!")
        return
    print("Memory map table found at offset %08X in the image." % mmh_offset)
    fp.seek(mmh_offset)
    mmh = MemoryMapHeader(fp.read(0x18))
    mmt = []
    while len(mmt) < mmh.count:
        e = MemoryMapEntry(fp.read(0x18))
        e.name = e.name.rstrip("\0")
        mmt.append(e)
    if mmt is None:
        return

    print("Figuring out the address of the BootExt object...")
    image_base = None
    for mme in mmt:
        if mme.type1 == 1 and mme.name == 'BootExt':
            image_base = mme.address - 0x30
            break
    if image_base is None:
        print("No BootExt section -- can't figure out where the image is based")
        return
    print("The image is based at %08X in the address space." % image_base)

    if args.prefix is None:
        out_prefix = os.path.splitext(os.path.basename(args.input_file))[0]
    else:
        out_prefix = args.prefix

    for mme in mmt:
        print('')
        print("Object: " + str(mme))

        if mme.type1 & 0x80:
            print("-> RAM object, nothing to write out.")
            continue

        offset = mme.address - image_base
        if offset < 0 or offset >= image_size:
            print("-> No data in the image for this object, skipped.")
            continue

        out_name = out_prefix + '_' + mme.name

        try:
            fp.seek(offset)
            sh = RomIoHeader(fp.read(0x30))
            print("-> ZyNOS ROMIO header found, version string: %s." % sh.version.strip("\0"))
            #print(str(sh))
            if sh.flags & 0x80:
                print("-> Data is compressed, compressed/original length: %08X/%08X." % (sh.comp_length, sh.orig_length))
                data_length = sh.comp_length
                # TODO: Figure out why +3 is required.
                tag = fp.read(3)
                fp.seek(-3, 1)
                if tag == "\0\0\0":
                    out_name += '.7z'
                    print("-> Compression method: LZMA?")
                    fp.seek(3, 1)
                elif tag == "]\0\0":
                    out_name += '.7z'
                    print("-> Compression method: LZMA")
                elif tag == "BZh":
                    out_name += '.bz2'
                    print("-> Compression method: bzip2")
                else:
                    print("-> Compression method: UNKNOWN")
            else:
                print("-> Data is not compressed, length: %08X." % sh.orig_length)
                data_length = sh.orig_length
        except ValueError:
            fp.seek(offset)
            data_length = mme.length
            print("-> Raw data.")

        data = fp.read(data_length)
        if len(data) != data_length:
            print("-> NOTE: not all data is in the image.")
        if not args.dry_run:
            print("-> Writing %d bytes to '%s'." % (data_length, out_name))
            out_fp = open(out_name, 'wb')
            out_fp.write(data)
            out_fp.close()
        else:
            print("-> Would write %d bytes to '%s'." % (data_length, out_name))
#
def do_pack(args):
    print("Currently not implemented, sorry.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    
    parser_unpack = subparsers.add_parser('unpack', help='unpack the firmware')
    parser_unpack.add_argument('input_file')
    parser_unpack.add_argument('--prefix',
        help="prefix for unpacked files (default: <basename>_)",
        default=None)
    parser_unpack.add_argument('--dry-run',
        help="don't actually do anything, just print",
        action='store_true',
        dest='dry_run',
        default=False)
    parser_unpack.set_defaults(do=do_unpack)

    parser_pack = subparsers.add_parser('pack', help='pack the firmware')
    parser_pack.set_defaults(do=do_pack)
    
    print("ZyNOS firmware tool by dev_zzo, version 0")
    print('')

    args = parser.parse_args()
    args.do(args)

    print('')
    print("Done.")
