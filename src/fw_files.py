"""Fictional attachment generators (standard library only; Pillow used only for the optional JPEG).
Every PNG/SVG/PDF carries a visible 'SAMPLE - FICTIONAL DATA' mark."""
import gzip
import random
import struct
import zlib

MARK = "SAMPLE - FICTIONAL DATA"

_G = {
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    " ": ["....."] * 7,
}

MIME = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf", "txt": "text/plain",
        "csv": "text/csv", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gz": "application/gzip"}


def mime_for(filename):
    if "." not in filename:
        return "application/octet-stream"
    return MIME.get(filename.rsplit(".", 1)[1].lower(), "application/octet-stream")


def _banner_rows(w, scale):
    """Return list of RGB row bytes (white background, dark red glyphs) for the mark."""
    text_w = len(MARK) * 6 * scale
    pad = 3 * scale
    h = 7 * scale + 2 * pad
    x0 = max(0, (w - text_w) // 2)
    rows = []
    for y in range(h):
        row = bytearray(b"\xff" * (w * 3))
        gy = (y - pad) // scale
        if 0 <= (y - pad) and 0 <= gy < 7:
            for ci, ch in enumerate(MARK):
                g = _G[ch][gy]
                for gx in range(5):
                    if g[gx] == "#":
                        for sx in range(scale):
                            px = x0 + (ci * 6 + gx) * scale + sx
                            if px < w:
                                row[px * 3:px * 3 + 3] = b"\xb0\x10\x10"
        rows.append(bytes(row))
    return rows


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)


def png(w, h, body_row, level=6, exact_size=None):
    """body_row(y) -> bytes of w*3.  The mark banner replaces the bottom rows.  Optional exact byte size."""
    scale = max(1, w // (len(MARK) * 6 + 12))
    banner = _banner_rows(w, scale)
    bh = len(banner)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += banner[y - (h - bh)] if y >= h - bh else body_row(y)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(bytes(raw), level))
    iend = _chunk(b"IEND", b"")
    out = sig + ihdr + idat + iend
    if exact_size:
        need = exact_size - len(out)
        if need < 0:
            raise ValueError("png larger than exact_size")
        if need:
            if need < 20:
                raise ValueError("cannot pad png by %d bytes" % need)
            filler = b"Comment\x00" + b"x" * (need - 12 - 8)
            out = sig + ihdr + _chunk(b"tEXt", filler) + idat + iend
    return out


def png_gradient(w, h, rgb, level=9):
    r, g, b = rgb

    def row(y):
        t = y / max(1, h - 1)
        return bytes([int(r * (1 - t) + 255 * t) & 255, int(g * (1 - t) + 230 * t) & 255, int(b * (1 - t) + 210 * t) & 255]) * w
    return png(w, h, row, level)


def png_noise(w, h, seed, exact_size=None):
    rnd = random.Random(seed)

    def row(y):
        return rnd.randbytes(w * 3)
    return png(w, h, row, level=1, exact_size=exact_size)


def svg(title, rgb=(40, 60, 120)):
    t = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="140" viewBox="0 0 360 140">\n'
            '  <rect width="360" height="140" fill="rgb(%d,%d,%d)"/>\n'
            '  <circle cx="60" cy="60" r="34" fill="#f2e6c9"/>\n'
            '  <text x="110" y="64" font-family="Georgia, serif" font-size="20" fill="#ffffff">%s</text>\n'
            '  <rect x="0" y="108" width="360" height="32" fill="#ffffff"/>\n'
            '  <text x="180" y="130" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="bold" fill="#b01010">%s</text>\n'
            '</svg>\n') % (rgb + (t, MARK))).encode("utf-8")


def _pdf_esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(lines, filler_bytes=0):
    """Hand-written single-page PDF. lines: list of str (latin-1 safe). Optional unreferenced filler object."""
    content = ["BT /F2 20 Tf 50 800 Td (%s) Tj ET" % MARK]
    y = 770
    for ln in lines:
        content.append("BT /F1 11 Tf 50 %d Td (%s) Tj ET" % (y, _pdf_esc(ln.encode("latin-1", "replace").decode("latin-1"))))
        y -= 15
        if y < 60:
            break
    content.append("BT /F2 12 Tf 50 40 Td (%s) Tj ET" % MARK)
    stream = "\n".join(content).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 5 0 R "
        b"/Resources << /Font << /F1 4 0 R /F2 6 0 R >> >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    if filler_bytes:
        blob = (b"SAMPLE-FICTIONAL-DATA-FILLER-" * (filler_bytes // 29 + 1))[:filler_bytes]
        objs.append(b"<< /Length %d >>\nstream\n" % len(blob) + blob + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def txt(text):
    return (MARK + "\n" + text + "\n").encode("utf-8")


def csv_bytes(rows):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["note"])
    w.writerow([MARK])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def gz(data):
    return gzip.compress(data, mtime=0)


def jpeg(seed, label):
    """Optional: only when Pillow is already installed."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    import io
    im = Image.new("RGB", (320, 120), (30 + seed % 100, 60, 90))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 90, 320, 120], fill=(255, 255, 255))
    d.text((10, 98), MARK, fill=(176, 16, 16))
    d.text((10, 10), label, fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return b.getvalue()
