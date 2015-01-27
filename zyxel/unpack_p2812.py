"""
Firmware image unpacker for ZyXEL models:
* P-2612HNU-F1
* P-2812HNU-F1

The firmware uses Yaffs2 with embedded squashFS.

Layout:
* Bootloader (Z-Boot)
* Yaffs2 partition
* XML config
* Unknown, marked with "V1.00(AACC.3)"
* MIPS Linux-2.6.32 image
* Unknown data

"""

import sys
import os
import struct

# Ref: http://www.aleph1.co.uk/gitweb?p=yaffs2.git;a=blob;f=yaffs_guts.h

YAFFS_OBJECT_TYPE_UNKNOWN = 0
YAFFS_OBJECT_TYPE_FILE = 1
YAFFS_OBJECT_TYPE_SYMLINK = 2
YAFFS_OBJECT_TYPE_DIRECTORY = 3
YAFFS_OBJECT_TYPE_HARDLINK = 4
YAFFS_OBJECT_TYPE_SPECIAL = 5

YAFFS_OBJECTID_ROOT = 1
YAFFS_OBJECTID_LOSTNFOUND = 2
YAFFS_OBJECTID_UNLINKED = 3
YAFFS_OBJECTID_DELETED = 4

def yaffs2_obj_unpack(data, endianness='be'):
    endian = '>' if endianness == 'be' else '<'
    fmt = endian + 'IIxx255s3xIIIIIIII159sxIQQQIII4xII'
    values = struct.unpack(fmt, data)
    obj = {
        'type': values[0],
        'parent_obj_id': values[1],
        'name': values[2].rstrip("\0"),
        'yst_mode': values[3],
        'yst_uid': values[4],
        'yst_gid': values[5],
        'yst_atime': values[6],
        'yst_mtime': values[7],
        'yst_ctime': values[8],
        'file_size_low': values[9],
        'equiv_id': values[10],
        'alias': values[11].rstrip("\0"),
        'yst_rdev': values[12],
        'win_ctime': values[13],
        'win_atime': values[14],
        'win_mtime': values[15],
        'inband_shadowed_obj_id': values[16],
        'inband_is_shrink': values[17],
        'file_size_high': values[18],
        'shadows_obj': values[19],
        'is_shrink': values[20],
    }
    return obj


def usage():
    print "Usage: %s <image file>" % (sys.argv[0])


try:
    imgpath = sys.argv[1]
except IndexError:
    usage()
    exit(1)

try:
    imgfp = open(sys.argv[1])
except:
    print "Failed to open the image."
    exit(2)


dry_run = False

# Flash geometry defs. Might change for other devices.
geometry = {
    'page_size': 0x840,
    'data_size': 0x800,
}

# These taken by the Z-Boot bootloader.
zboot_pages = 0x40

imgfp.seek(zboot_pages * geometry['page_size'])
headers = []

while True:
    #print "at: %08x" % imgfp.tell()
    page = imgfp.read(geometry['page_size'])
    if len(page) < geometry['page_size']:
        break

    # This is BS. Need to figure out a better way, but ATM there's nothing.
    if page[:5] == '<?xml' or page[3:8] == '<?xml':
        imgfp.seek(-geometry['page_size'], os.SEEK_CUR)
        break

    header = yaffs2_obj_unpack(page[:0x200])
    headers.append(header)
    print "type: %d name: '%s' parent: %x" % (header['type'], header['name'], header['parent_obj_id'])
    if header['name'] == '':
        print "(dummy entry)"
        continue

    path_chunks = []
    current_id = 0x100 + len(headers) - 1
    try:
        while current_id != YAFFS_OBJECTID_ROOT:
            hh = headers[current_id - 0x100]
            path_chunks.append(hh['name'])
            current_id = hh['parent_obj_id']
        obj_path = os.path.join(*reversed(path_chunks))
    except IndexError:
        print "Invalid current_id of %x" % (current_id)
        break

    if header['type'] == YAFFS_OBJECT_TYPE_FILE:
        print "%s (%d bytes)" % (obj_path, header['file_size_low'])

        if not dry_run:
            outfp = open(obj_path, 'wb')
        size = header['file_size_low']
        while size > 0:
            page = imgfp.read(geometry['page_size'])
            if not dry_run:
                outfp.write(page[:geometry['data_size']])
            size -= geometry['data_size']
        if not dry_run:
            outfp.close()

    elif header['type'] == YAFFS_OBJECT_TYPE_SYMLINK:
        print "%s -> %s" % (obj_path, header['alias'])

        if not dry_run:
            os.symlink(header['alias'], obj_path)

    elif header['type'] == YAFFS_OBJECT_TYPE_DIRECTORY:
        print "%s" % (obj_path)

        if not dry_run:
            os.mkdir(obj_path, header['yst_mode'])

    elif header['type'] == YAFFS_OBJECT_TYPE_SPECIAL:
        major = header['yst_rdev'] >> 8
        minor = header['yst_rdev'] & 0xFF
        print "%s (%d,%d)" % (obj_path, major, minor)

        # If cannot create the device -- ignore it.
        try:
            if not dry_run:
                os.mknod(obj_path, header['yst_mode'], os.makedev(major, minor))
        except OSError:
            pass

    #elif header['type'] == YAFFS_OBJECT_TYPE_HARDLINK:
    else:
        print "%s (not handled, dumping)" % (obj_path)
        print repr(header)
