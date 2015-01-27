"""
A simple tool to make certain ZyXEL firmware images workable.

Some images (see list below for applicable models) are prepared to be 
written to NAND which is organized as 0x800 bytes data + 0x40 bytes extra.

Applicable models:
* P-2612HNU-F1
* P-2812HNU-F1
* Feel free to add

"""

import sys

useful_size = 0x800
discard_size = 0x40

print 'ZyXEL NAND Image Depager Tool'
print 'Data/page = 0x%x bytes, Waste/page = 0x%x bytes' % (useful_size, discard_size)

with open(sys.argv[1], 'rb') as infile, open(sys.argv[2], 'wb') as outfile:
    page_size = useful_size + discard_size
    while True:
        page = infile.read(page_size)
        data_len = len(page)
        if data_len < page_size:
            if data_len > 0:
                print 'NOTE: last page size was %d, not handled properly' % data_len
            break
        outfile.write(page[:useful_size])
print 'Done.'
