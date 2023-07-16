"""
A tool for ZyNOS firmware update binaries.

References:
https://dev.openwrt.org/browser/trunk/tools/firmware-utils/src/zynos.h
http://www.ixo.de/info/zyxel_uclinux/

"""

import argparse
import os.path
import sys
import struct
import bz2

import subprocess
def decompress_lzma(data):
    p = subprocess.Popen(['lzma', '-d'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=False)
    r = p.communicate(data)
    return r[0]
def compress_lzma(data):
    p = subprocess.Popen(['lzma', '-e', '-d23'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=False)
    r = p.communicate(data)
    return r[0]
def decompress_bz2(data):
    return bz2.decompress(data)
def compress_bz2(data):
    return bz2.compress(data)
#

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
        lines.append("  Type: %02X" % self.type)
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

    if args.prefix is None:
        out_prefix = os.path.basename(args.input_file) + '.unpacked'
    else:
        out_prefix = args.prefix
    print("Using '%s' as output path prefix." % out_prefix)

    if not args.dry_run:
        if os.path.exists(out_prefix):
            if not os.path.isdir(out_prefix):
                print("Output path already exists and is not a directory; can't write there.")
                return
            else:
                print("Output path already exists; writing there.")
        else:
            try:
                os.mkdir(out_prefix)
            except OSError:
                print("Failed to create output path.")
                return

    print("Searching for memory map table...")
    fp.seek(0, 2)
    size = fp.tell()
    mmh_offset = 0x100
    mmh = MemoryMapHeader()
    while mmh_offset < size - 0x100:
        fp.seek(mmh_offset)
        mmh.unpack(fp.read(0x18))
        mmt_size = (mmh.count + 1) * 0x18
        calculated_addr = mmh.user_start - mmt_size
        if calculated_addr == romio_header.mmap_addr:
            mmt_length = mmh.user_end - romio_header.mmap_addr - 0x18
            if 0 <= mmt_length < size - mmh_offset:
                if checksum(fp.read(mmt_length)) == mmh.checksum:
                    print("Memory map table found at offset %08X in the image." % mmh_offset)
                    break
        mmh_offset += 0x100
    else:
        print("Memory map table not found!")
        return

    fp.seek(mmh_offset + 0x18)
    mmt = []
    while len(mmt) < mmh.count:
        e = MemoryMapEntry(fp.read(0x18))
        e.name = e.name.rstrip("\0")
        mmt.append(e)
    if not args.dry_run:
        with open(out_prefix + '/.map', 'wt') as out:
            out.write("[\n")
            out.write("# Name, Address, Size, Type1, Type2\n")
            for mme in mmt:
                out.write("('%s', 0x%08XL, 0x%08XL, %d, %d),\n" % (mme.name, mme.address, mme.length, mme.type1, mme.type2))
            out.write("]\n")
    if romio_header.mmap_addr + mmt_size == mmh.user_start:
        user = fp.read(mmh.user_end - mmh.user_start + 1)
        if not args.dry_run:
            out_name = out_prefix + '/.user'
            print("Writing %d bytes of $USER data to '%s'" % (len(user), out_name))
            with open(out_name, 'wb') as out:
                out.write(user)
    else:
        # Don't know how best to deal with this for now.
        print("USER data is not located after memory map table.")

    # To tie the image to a memory location, figure out where BootExt is located.
    # The image base is then that address minus 0x30 for ROMIO header.
    print("Figuring out the address of the BootExt object...")
    for mme in mmt:
        if mme.type1 == 1 and mme.name == 'BootExt':
            image_base = mme.address - 0x30
            print("The image is based at %08X in the address space." % image_base)
            break
    else:
        print("No BootExt section -- can't figure out where the image is based")
        return

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

        out_name = out_prefix + '/' + mme.name

        if mme.type1 == 4:
            # ROMBIN: (compressed) image with ROMIO header
            fp.seek(offset)
            sh = RomIoHeader(fp.read(0x30))
            print("-> ZyNOS ROMIO header found, version string: %s." % sh.version.strip("\0"))
            if sh.flags & 0x80:
                print("-> Data is compressed, compressed/original length: %08X/%08X." % (sh.comp_length, sh.orig_length))
                df = None
                tag = fp.read(3)
                if tag == "\0\0\0":
                    # Some firmware requires 3 zero bytes before actual LZMA data...
                    tag = fp.read(3)
                    if tag == "]\0\0":
                        print("-> Compression method: LZMA (3 zeros prepended)")
                        df = decompress_lzma
                        fp.seek(-3, 1)
                    else:
                        print("-> Compression method: UNKNOWN")
                        fp.seek(-6, 1)
                elif tag == "]\0\0":
                    print("-> Compression method: LZMA")
                    df = decompress_lzma
                    fp.seek(-3, 1)
                elif tag == "BZh":
                    print("-> Compression method: bzip2")
                    df = decompress_bz2
                    fp.seek(-3, 1)
                else:
                    print("-> Compression method: UNKNOWN")
                    fp.seek(-3, 1)
                data = fp.read(sh.comp_length)
                
                if df:
                    data = df(data)

                if not args.dry_run:
                    out_fp = open(out_name, 'wb')
                    out_fp.write(data)
                    out_fp.close()
                
                data_length = sh.comp_length + 0x30
            else:
                print("-> Data is not compressed, length: %08X." % sh.orig_length)
                data_length = sh.orig_length + 0x30
            out_name += '.rom'
        else:
            # Everything else:
            print("-> Raw data.")

        data_length = mme.length
        fp.seek(offset)
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
    return
#
def read_map(map_path):
    with open(map_path, 'r') as fp:
        mmt_source = eval(fp.read())
    mmt = []
    for x in mmt_source:
        y = MemoryMapEntry()
        y.name, y.address, y.length, y.type1, y.type2 = x
        mmt.append(y)
    return mmt
#
def read_comp(comp_path):
    try:
        with open(comp_path, 'r') as fp:
            return eval(fp.read())
    except IOError:
        return {}
#
def pad_data(data):
    tail = len(data) & 0x3FF
    if tail > 0:
        data += "\0" * (0x400 - tail)
    return data
#
def do_pack(args):
    print("Reading memory map file.")
    ram_objects = []
    rom_objects = []
    rom_objects_with_data = []
    mmt_address = None
    be_rom_address = None
    be_ram_address = None
    for x in read_map(os.path.join(args.input_dir, '.map')):
        if x.type1 & 0x80:
            ram_objects.append(x)
        else:
            rom_objects.append(x)
        if x.type1 == 7:
            mmt_address = x.address
        elif x.name == 'BootExt':
            if x.type1 == 1:
                be_rom_address = x.address
                image_base = be_rom_address - 0x30
            else:
                be_ram_address = x.address
        if be_rom_address is not None and x.address >= be_rom_address:
            rom_objects_with_data.append(x)
    if mmt_address is None:
        print("Could not find memory map table address in that file.")
        return
    if be_rom_address is None:
        print("Could not find boot extension address in ROM in that file.")
        return
    if be_ram_address is None:
        print("Could not find boot extension address in RAM in that file.")
        return
    print("Image base address: %08X" % image_base)
    print("Boot extension address in RAM: %08X" % be_ram_address)
    print("Boot extension address in ROM: %08X" % be_rom_address)
    print("Objects in RAM:")
    for x in ram_objects:
        print(str(x))
    print("Objects in ROM:")
    for x in rom_objects:
        print(str(x))
    print('')
    
    mmt = []
    for x in ram_objects:
        mmt.append(x.pack())
    for x in rom_objects:
        mmt.append(x.pack())
    try:
        with open(os.path.join(args.input_dir, '.user'), 'rb') as fp:
            user = fp.read()
        mmt.append(user)
    except IOError:
        user = None
    mmh = MemoryMapHeader()
    mmh.count = len(ram_objects) + len(rom_objects)
    if user:
        mmh.user_start = mmt_address + (1 + mmh.count) * 0x18
        mmh.user_end = mmh.user_start + len(user) - 1
    mmt_data = ''.join(mmt)
    mmh.checksum = checksum(mmt_data)
    mmt_data = pad_data(mmh.pack() + mmt_data)

    comp = read_comp(os.path.join(args.input_dir, '.comp'))
    out_fp = open('ras', 'w+b')
    out_fp.write("\0" * 0x30)
    try:
        for mme in rom_objects_with_data:
            print("Writing '%s'..." % mme.name)
            if mme.type1 == 1:
                # ROMIMG
                path = os.path.join(args.input_dir, mme.name)
                try:
                    print("Trying '%s'..." % path)
                    fp = open(path, 'rb')
                except IOError:
                    print("WARN: Could not open the source object binary, not written")
                    continue
                out_fp.seek(mme.address - image_base, 0)
                out_fp.write(fp.read())
                fp.close()
            elif mme.type1 == 4:
                # ROMBIN
                path = os.path.join(args.input_dir, mme.name + '.rom')
                try:
                    print("Trying '%s'..." % path)
                    fp = open(path, 'rb')
                except IOError:
                    print("WARN: Could not open the source object binary, not written")
                    continue
                out_fp.seek(mme.address - image_base, 0)
                out_fp.write(fp.read())
                fp.close()
            elif mme.type1 == 7:
                # ROMMAP
                out_fp.write(mmt_data)
            else:
                print("Don't know how to write object type %d!" % mme.type1)
    except:
        out_fp.close()
    print("Updating ROMIO header...")
    hdr = RomIoHeader()
    hdr.type = 3
    hdr.flags = 0x40
    hdr.load_addr = be_ram_address
    hdr.mmap_addr = mmt_address
    out_fp.seek(0x30, 0)
    data = out_fp.read()
    hdr.orig_length = len(data)
    hdr.orig_checksum = checksum(data)
    out_fp.seek(0, 0)
    out_fp.write(hdr.pack())
    out_fp.close()
#
def do_romio(args):
    with open(args.input_file, 'rb') as fp:
        data = fp.read()
    hdr = RomIoHeader()
    hdr.type = args.type
    hdr.flags = 0x20
    hdr.orig_length = len(data)
    hdr.orig_checksum = checksum(data)
    hdr.version = args.version
    print("Input length: %08X, checksum: %04X" % (hdr.orig_length, hdr.orig_checksum))
    if args.compression:
        hdr.flags |= 0xC0
        if args.compression == 'lzma' or args.compression == 'lzma0':
            data = compress_lzma(data)
            # Fix: splice in the file size
            data = data[:5] + struct.pack('<Q', hdr.orig_length) + data[13:]
        elif args.compression == 'bzip2':
            data = compress_bz2(data)
        else:
            print("Unrecognized compression method requested: '%s'" % args.compression)
            return
        hdr.comp_length = len(data)
        hdr.comp_checksum = checksum(data)
        print("Compressed length: %08X, checksum: %04X" % (hdr.comp_length, hdr.comp_checksum))
        if args.compression == 'lzma0':
            data = "\0\0\0" + data
    with open(args.output, 'wb') as fp:
        fp.write(hdr.pack())
        fp.write(data)
#
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    
    parser_unpack = subparsers.add_parser('unpack', help='unpack the firmware')
    parser_unpack.add_argument('input_file')
    parser_unpack.add_argument('--prefix',
        help="path for unpacked files (default: <filename>.unpacked)",
        default=None)
    parser_unpack.add_argument('--dry-run',
        help="don't actually do anything, just print",
        action='store_true',
        dest='dry_run',
        default=False)
    parser_unpack.set_defaults(do=do_unpack)

    parser_pack = subparsers.add_parser('pack', help='pack the firmware')
    parser_pack.add_argument('input_dir')
    parser_pack.set_defaults(do=do_pack)

    parser_romio = subparsers.add_parser('romio', help='make ROMIO file')
    parser_romio.add_argument('input_file')
    parser_romio.add_argument('--type',
        type=int,
        default=4)
    parser_romio.add_argument('--flags',
        type=int,
        default=0x40)
    parser_romio.add_argument('--version',
        default='')
    parser_romio.add_argument('--output',
        default='object.rom')
    parser_romio.add_argument('--compression',
        default=None)
    parser_romio.set_defaults(do=do_romio)
    
    print("ZyNOS firmware tool by dev_zzo, version 1")
    print('')

    args = parser.parse_args()
    args.do(args)

    print('')
    print("Done.")
