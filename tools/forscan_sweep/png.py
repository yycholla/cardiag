"""Minimal PNG read/crop/write for 8-bit RGB/RGBA non-interlaced images."""
import struct, zlib

def read(path):
    data = open(path, 'rb').read()
    pos, chunks = 8, []
    w = h = bpp = None
    idat = b''
    while pos < len(data):
        n, = struct.unpack('>I', data[pos:pos+4]); kind = data[pos+4:pos+8]
        body = data[pos+8:pos+8+n]; pos += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', body[:10])
            bpp = {2: 3, 6: 4}[ctype]
        elif kind == b'IDAT':
            idat += body
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i+1:i+1+stride]); i += 1 + stride
        for x in range(stride):
            a = line[x-bpp] if x >= bpp else 0
            b = prev[x]; c = prev[x-bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line)); prev = line
    return w, h, bpp, rows

def pixel(img, x, y):
    w, h, bpp, rows = img
    return tuple(rows[y][x*bpp:x*bpp+3])

def write_crop(img, box, path, scale=2):
    w, h, bpp, rows = img
    x0, y0, x1, y1 = box
    out = b''
    for y in range(y0, y1):
        line = b''.join(rows[y][x*bpp:x*bpp+3] * scale for x in range(x0, x1))
        out += (b'\x00' + line) * scale
    cw, ch = (x1-x0)*scale, (y1-y0)*scale
    def chunk(k, b): return struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k+b) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', cw, ch, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(out)) + chunk(b'IEND', b''))


def binarize(img, box):
    """Black text on white for a list box, whether a row is highlighted or not."""
    w, h, bpp, rows = img
    x0, y0, x1, y1 = box
    out = []
    for y in range(y0, y1):
        px = [rows[y][x*bpp:x*bpp+3] for x in range(x0, x1)]
        blue_row = sum(1 for r, g, b in px if b - r > 80) > len(px) // 2
        line = bytearray()
        for r, g, b in px:
            lum = (r + g + b) // 3
            dark = lum > 200 if blue_row else lum < 140
            line += b"\x00\x00\x00" if dark else b"\xff\xff\xff"
        out.append(bytes(line))
    return (x1 - x0, y1 - y0, 3, out)
