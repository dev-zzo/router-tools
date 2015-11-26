"""
Firmware image unpacker for ZyXEL models:
* P-2612HNU-F1
* P-2812HNU-F1
* P-2812HNU-F3 (1.00+)

The firmware uses Yaffs2 with embedded squashFS.

Layout:
* Bootloader (Z-Boot)
* Yaffs2 partition
* XML config
* Unknown, marked with "V1.00(AACC.3)"
* MIPS Linux-2.6.32 image
* Unknown data

"""

import argparse
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
YAFFS_OBJECT_TYPE_MAX = 6

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

def unpack_next(fp, args, headers):
    page = imgfp.read(args.page_size)
    if len(page) < args.page_size:
        return False

    # This is BS. Need to figure out a better way, but ATM there's nothing.
    if page[:5] == '<?xml' or page[3:8] == '<?xml':
        imgfp.seek(-args.page_size, os.SEEK_CUR)
        return False

    header = yaffs2_obj_unpack(page[:0x200])
    if not (YAFFS_OBJECT_TYPE_UNKNOWN <= header['type'] < YAFFS_OBJECT_TYPE_MAX):
        print "Invalid object type %08x" % (header['type'])
        return False

    headers.append(header)
    print "type: %d name: '%s' parent: %x" % (header['type'], header['name'], header['parent_obj_id'])
    if header['name'] == '':
        print "(dummy entry)"
        return True

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
        return False

    if header['type'] == YAFFS_OBJECT_TYPE_FILE:
        print "%s (%d bytes)" % (obj_path, header['file_size_low'])

        if not args.dry_run:
            outfp = open(obj_path, 'wb')
        size = header['file_size_low']
        while size > 0:
            page = imgfp.read(args.page_size)
            if not args.dry_run:
                outfp.write(page[:args.data_size])
            size -= args.data_size
        if not args.dry_run:
            outfp.close()

    elif header['type'] == YAFFS_OBJECT_TYPE_SYMLINK:
        print "%s -> %s" % (obj_path, header['alias'])

        if not args.dry_run:
            os.symlink(header['alias'], obj_path)

    elif header['type'] == YAFFS_OBJECT_TYPE_DIRECTORY:
        print "%s" % (obj_path)

        if not args.dry_run:
            os.mkdir(obj_path, header['yst_mode'])

    elif header['type'] == YAFFS_OBJECT_TYPE_SPECIAL:
        major = header['yst_rdev'] >> 8
        minor = header['yst_rdev'] & 0xFF
        print "%s (%d,%d)" % (obj_path, major, minor)

        # If cannot create the device -- ignore it.
        try:
            if not args.dry_run:
                os.mknod(obj_path, header['yst_mode'], os.makedev(major, minor))
        except OSError:
            pass

    #elif header['type'] == YAFFS_OBJECT_TYPE_HARDLINK:
    else:
        print "%s (not handled, dumping)" % (obj_path)
        print repr(header)
    return True

def num(x):
    return int(x, 0)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('image_path',
        help='path to an image file to handle')
    parser.add_argument('--dry-run',
        action='store_true',
        help='do not write anything')
    parser.add_argument('--page-size',
        dest='page_size',
        type=num,
        default=0x840,
        help='flash page size, in hex')
    parser.add_argument('--data-size',
        dest='data_size',
        type=num,
        default=0x800,
        help='flash data size, in hex')
    parser.add_argument('--boot-pages',
        dest='boot_pages',
        type=num,
        default=0x40,
        help='number of pages taken by zboot')
    args = parser.parse_args()

    imgfp = open(args.image_path)
    imgfp.seek(args.boot_pages * args.page_size)
    headers = []

    while unpack_next(imgfp, args, headers):
        pass
    print "Done."
# EOF
