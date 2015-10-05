"""
An overly simplistic tool to decompress rom-0 files.
It probably does not work correctly.
Still, it produces some useful output.
"""

import sys
import struct
import lzs

def process_spt(fp):
    magic, h1, h2, h3 = struct.unpack('>IHHI', fp.read(12))
    if header[0] != 0xCEEDDBDBL:
        print "Magic number doesn't match."
        return
    ofp = open('spt.dat', 'wb')
    w = lzs.RingList(2048)
    while True:
        header2 = struct.unpack('>HH', fp.read(4))
        if header2[0] != 0x0800:
            break
        print "Compressed block: %04X, length %04X" % header2
        data = fp.read(header2[1])
        dd = lzs.decompress(data, w)
        #print hexdump(dd)
        ofp.write(dd)
        #break
    ofp.close()

def process_block(fp):
    block_offset = fp.tell()
    block_id, block_entries, block_unk = struct.unpack('>BxHH', fp.read(6))
    print "Block %d, entries: %d, unk: %04X" % (block_id, block_entries, block_unk)
    while block_entries > 0:
        e = struct.unpack('>14sHHH', fp.read(20))
        print "Entry: %s Length: %04X %04X Offset: %04X" % e
        name, length, unknown, offset = e
        name = name.strip('\0')
        
        next_offset = fp.tell()
        fp.seek(block_offset + offset, 0)
        if name == 'spt.dat':
            process_spt(fp)
        fp.seek(next_offset, 0)
        
        block_entries -= 1

fp = open(sys.argv[1], 'rb')
fp.seek(8192, 0)
process_block(fp)
