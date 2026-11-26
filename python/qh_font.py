"""3x5 pixel font and drawing helpers for the 13x8 LED matrix."""

# Each glyph is 5 rows, '#' = lit. The width comes from the row length.
_G = {
    "0": ["###", "#.#", "#.#", "#.#", "###"],
    "1": [".#", "##", ".#", ".#", ".#"],
    "2": ["###", "..#", "###", "#..", "###"],
    "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"],
    "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"],
    "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"],
    "9": ["###", "#.#", "###", "..#", "###"],
    "A": [".#.", "#.#", "###", "#.#", "#.#"],
    "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"],
    "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
    "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    "Z": ["###", "..#", ".#.", "#..", "###"],
    " ": ["..", "..", "..", "..", ".."],
    ".": [".", ".", ".", ".", "#"],
    ",": [".", ".", ".", "#", "#"],
    ":": [".", "#", ".", "#", "."],
    "!": ["#", "#", "#", ".", "#"],
    "'": ["#", "#", ".", ".", "."],
    "-": ["...", "...", "###", "...", "..."],
    "+": ["...", ".#.", "###", ".#.", "..."],
    "=": ["...", "###", "...", "###", "..."],
    "/": ["..#", "..#", ".#.", "#..", "#.."],
    "%": ["#.#", "..#", ".#.", "#..", "#.#"],
    "?": ["##.", "..#", ".#.", "...", ".#."],
    "<": ["..#", ".#.", "#..", ".#.", "..#"],
    ">": ["#..", ".#.", "..#", ".#.", "#.."],
    "(": [".#", "#.", "#.", "#.", ".#"],
    ")": ["#.", ".#", ".#", ".#", "#."],
    "°": ["##", "##", "..", "..", ".."],
}
_TR = str.maketrans({"ç": "C", "Ç": "C", "ğ": "G", "Ğ": "G", "ı": "I", "İ": "I",
                     "ö": "O", "Ö": "O", "ş": "S", "Ş": "S", "ü": "U", "Ü": "U"})

W, H = 13, 8
TOP = 1  # first row used by text


def text_columns(text):
    """Turn text into a list of columns; each column is 5 booleans."""
    cols = []
    for ch in text.translate(_TR).upper():
        g = _G.get(ch, _G["?"])
        width = len(g[0])
        for x in range(width):
            cols.append([g[y][x] == "#" for y in range(5)])
        cols.append([False] * 5)  # gap between letters
    if cols:
        cols.pop()
    return cols


def render(cols, offset, level):
    """Build a 104-character frame (13x8) from a column list."""
    px = ["0"] * (W * H)
    on = str(max(1, min(7, int(level))))
    for x in range(W):
        cx = x + offset
        if 0 <= cx < len(cols):
            for y in range(5):
                if cols[cx][y]:
                    px[(TOP + y) * W + x] = on
    return "".join(px)


def centered(cols, level):
    off = -((W - len(cols)) // 2)
    return render(cols, off, level)


def blank():
    return "0" * (W * H)


# ---------------------------------------------------------------- matrix modes
MODES = ("text", "clock", "value", "bar", "anim", "icon", "status", "ip", "off")
ANIMS = ("heartbeat", "wave", "rain", "sparkle", "spinner", "bounce")

# 13 x 8 pictures, '#' = lit. Keep every row exactly 13 characters.
ICONS = {
    "smile": [
        "...#######...",
        "..#.......#..",
        ".#..#...#..#.",
        ".#.........#.",
        ".#.#.....#.#.",
        ".#..#####..#.",
        "..#.......#..",
        "...#######...",
    ],
    "sad": [
        "...#######...",
        "..#.......#..",
        ".#..#...#..#.",
        ".#.........#.",
        ".#..#####..#.",
        ".#.#.....#.#.",
        "..#.......#..",
        "...#######...",
    ],
    "heart": [
        "..###...###..",
        ".#####.#####.",
        ".###########.",
        ".###########.",
        "..#########..",
        "...#######...",
        "....#####....",
        "......#......",
    ],
    "check": [
        ".............",
        "...........#.",
        "..........##.",
        ".........##..",
        ".#......##...",
        ".##....##....",
        "..##..##.....",
        "...####......",
    ],
    "cross": [
        "..##.....##..",
        "...##...##...",
        "....##.##....",
        ".....###.....",
        ".....###.....",
        "....##.##....",
        "...##...##...",
        "..##.....##..",
    ],
    "wifi": [
        "..#########..",
        ".#.........#.",
        "#...#####...#",
        "...#.....#...",
        "..#..###..#..",
        "....#...#....",
        "......#......",
        "......#......",
    ],
    "house": [
        "......#......",
        ".....###.....",
        "....#####....",
        "...#######...",
        "..#########..",
        "...##...##...",
        "...##.#.##...",
        "...##.#.##...",
    ],
    "sun": [
        "......#......",
        ".#...###...#.",
        "...#######...",
        "#.#########.#",
        "#.#########.#",
        "...#######...",
        ".#...###...#.",
        "......#......",
    ],
    "moon": [
        "....####.....",
        "...###.......",
        "..###........",
        "..###........",
        "..###........",
        "..####....#..",
        "...########..",
        "....######...",
    ],
    "bell": [
        "......#......",
        ".....###.....",
        "....#####....",
        "....#####....",
        "...#######...",
        "..#########..",
        ".............",
        ".....###.....",
    ],
    "warn": [
        "......#......",
        ".....#.#.....",
        "....#.#.#....",
        "....#.#.#....",
        "...#..#..#...",
        "..#.......#..",
        ".#....#....#.",
        ".###########.",
    ],
    "lock": [
        ".....###.....",
        "....#...#....",
        "....#...#....",
        "...#######...",
        "...###.###...",
        "...###.###...",
        "...#######...",
        ".............",
    ],
    "up": [
        "......#......",
        ".....###.....",
        "....#####....",
        "...#######...",
        ".....###.....",
        ".....###.....",
        ".....###.....",
        ".....###.....",
    ],
    "down": [
        ".....###.....",
        ".....###.....",
        ".....###.....",
        ".....###.....",
        "...#######...",
        "....#####....",
        ".....###.....",
        "......#......",
    ],
}

# Narrow digits for the tens of the hour (only 1 and 2 ever appear there).
_NARROW = {"1": [".#", "##", ".#", ".#", ".#"], "2": ["##", ".#", "##", "#.", "##"]}
# One wave period, row of the crest for 12 successive columns (0 = top row).
_WAVE = (3, 5, 6, 7, 6, 5, 3, 2, 1, 0, 1, 2)
# Spinner path, clockwise, (x, y).
_RING = ((5, 1), (6, 1), (7, 1), (8, 2), (9, 3), (9, 4), (8, 5), (7, 6), (6, 6), (5, 6),
         (4, 5), (3, 4), (3, 3), (4, 2))
# Rain: start delay of the drop in each column, in steps.
_RAIN = (0, 7, 3, 9, 1, 5, 10, 2, 8, 4, 6, 1, 9)
# Heartbeat: brightness in eighths for 10 successive steps (two beats, then a rest).
_BEAT = (8, 4, 8, 4, 2, 2, 2, 2, 2, 2)


def _lv(level):
    return max(1, min(7, int(level)))


def _dim(level, num, den):
    """A dimmer shade of `level`, never fully off."""
    return max(1, _lv(level) * num // den)


def _frame(px):
    return "".join(str(v) for v in px)


def _put(px, glyph, x, y, level):
    for r, row in enumerate(glyph):
        for c, ch in enumerate(row):
            if ch == "#" and 0 <= x + c < W and 0 <= y + r < H:
                px[(y + r) * W + x + c] = level


def from_rows(rows, level=7):
    """8 strings of 13 characters ('#' lit, anything else dark) -> frame."""
    on = str(_lv(level))
    return "".join(on if ch == "#" else "0" for row in rows for ch in row.ljust(W)[:W])


def scale(frame, level):
    """Scale a frame drawn for brightness 7 down to `level` (lit pixels stay lit)."""
    lv = _lv(level)
    return "".join("0" if ch == "0" else str(max(1, int(ch) * lv // 7)) for ch in frame)


def icon(name, level=7):
    """Frame of a named icon, or None when the name is unknown."""
    rows = ICONS.get(name)
    return from_rows(rows, level) if rows else None


def scroll_offset(ncols, t, ms, t0=0.0):
    """Column offset of a scrolling text at time t. One pass = text enters at the right
    edge and leaves at the left: W + ncols steps of `ms` milliseconds."""
    span = W + ncols + 1
    return int(max(0.0, t - t0) * 1000.0 / max(1.0, ms)) % span - W


def text_frame(cols, t, ms, level, t0=0.0):
    """Centred when the columns fit on the matrix, otherwise scrolling by time."""
    if len(cols) <= W:
        return centered(cols, level)
    return render(cols, scroll_offset(len(cols), t, ms, t0), level)


def fit_value(value_text, unit):
    """Text for 'value' mode: with the unit when that fits without scrolling, else without."""
    v = str(value_text)
    if unit:
        for sep in (" ", ""):
            if len(text_columns(v + sep + unit)) <= W:
                return v + sep + unit
    return v


def clock(hour, minute, second, level, blink=True, h12=False):
    """HH MM on one line: hours bright, minutes dim, no leading zero on the hour.
    Four 3-wide digits with gaps need 15 columns, so the tens of the hour use a 2-wide
    digit and the brightness step replaces the colon column. Two dots under the gap
    blink once a second."""
    lv = _lv(level)
    lo = _dim(level, 1, 3)
    if lo == lv and lv > 1:
        lo = lv - 1
    if h12:
        hour = hour % 12 or 12
    px = [0] * (W * H)
    ht, ho = divmod(int(hour) % 24, 10)
    mt, mo = divmod(int(minute) % 60, 10)
    if ht:
        _put(px, _NARROW[str(ht)], 0, TOP, lv)
    for digit, right, shade in ((ho, 5, lv), (mt, 8, lo), (mo, 12, lo)):
        g = _G[str(digit)]
        _put(px, g, right - len(g[0]) + 1, TOP, shade)
    if not blink or int(second) % 2 == 0:
        px[7 * W + 5] = lv
        px[7 * W + 6] = lo
    return _frame(px)


def bar(frac, level):
    """Horizontal level bar, rows 2..5, 13 columns. The last column fades in."""
    lv = _lv(level)
    f = max(0.0, min(1.0, float(frac))) * W
    full = int(f)
    part = int(round((f - full) * lv))
    px = [0] * (W * H)
    for x in range(W):
        v = lv if x < full else (part if x == full else 0)
        for y in (2, 3, 4, 5):
            px[y * W + x] = v
        px[7 * W + x] = 1 if x in (0, 6, 12) else 0     # scale marks at 0, 50 and 100 %
    return _frame(px)


def graph(values, lo, hi, level):
    """Sparkline of up to 13 numbers (oldest first, newest in the right column).
    lo == hi means: scale to the smallest and largest value shown."""
    lv = _lv(level)
    fill = _dim(level, 1, 3)
    vals = [float(v) for v in list(values)[-W:]]
    if not vals:
        return blank()
    if lo == hi:
        lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    px = [0] * (W * H)
    x0 = W - len(vals)
    for i, v in enumerate(vals):
        top = (H - 1) - int(round(max(0.0, min(1.0, (v - lo) / span)) * (H - 1)))
        for y in range(top, H):
            px[y * W + x0 + i] = lv if y == top else fill
    return _frame(px)


def status(online, total, mqtt, t, level):
    """Boards online / total as text, one bottom-row pixel per board (first 13) and the
    MQTT state in the top right corner. `online` is a list of booleans, one per board.
    mqtt: True connected, False not connected (blinks), None switched off."""
    lv, lo = _lv(level), _dim(level, 1, 3)
    cols = text_columns("%d/%d" % (sum(1 for b in online if b), total))
    px = [int(ch) for ch in centered(cols, lv)] if len(cols) <= W else [0] * (W * H)
    for x, up in enumerate(list(online)[:W]):
        px[7 * W + x] = lv if up else (lo if int(t * 2) % 2 == 0 else 0)
    if mqtt is True or (mqtt is False and int(t * 2) % 2 == 0):
        px[0 * W + 12] = lv
    return _frame(px)


def _hash(i, k):
    """Repeatable pseudo-random number 0..255 for pixel i at step k."""
    h = (i * 7919 + k * 104729 + 1) & 0xFFFFFFFF
    h ^= h >> 7
    h = (h * 2654435761) & 0xFFFFFFFF
    return (h >> 16) & 255


def anim_step(t, speed=5):
    """Frame counter of an animation: speed 1 = 2 frames a second, speed 9 = 10."""
    return int(max(0.0, t) * (1 + max(1, min(9, int(speed)))))


def anim(name, t, level, speed=5):
    """Frame of a named animation at time t (seconds). Unknown names give a blank frame."""
    lv = _lv(level)
    k = anim_step(t, speed)
    px = [0] * (W * H)
    if name == "heartbeat":
        return scale(icon("heart", 7), max(1, lv * _BEAT[k % len(_BEAT)] // 8))
    if name == "wave":
        for x in range(W):
            y = _WAVE[(x + k) % len(_WAVE)]
            px[y * W + x] = lv
            if y + 1 < H:
                px[(y + 1) * W + x] = _dim(level, 1, 3)
    elif name == "rain":
        for x in range(W):
            head = (k + _RAIN[x]) % 11              # 8 rows on screen, 3 steps of pause
            for back, shade in ((0, lv), (1, _dim(level, 1, 2)), (2, _dim(level, 1, 4))):
                y = head - back
                if 0 <= y < H:
                    px[y * W + x] = shade
    elif name == "sparkle":
        for i in range(W * H):
            for age, shade in ((0, lv), (1, _dim(level, 1, 3))):
                if _hash(i, k - age) < 14 and not px[i]:      # about 5 % of the pixels
                    px[i] = shade
    elif name == "spinner":
        n = len(_RING)
        for back, shade in ((4, _dim(level, 1, 7)), (3, _dim(level, 2, 7)), (2, _dim(level, 3, 7)),
                            (1, _dim(level, 5, 7)), (0, lv)):
            x, y = _RING[(k - back) % n]
            px[y * W + x] = shade
    elif name == "bounce":
        def tri(n, m):
            return m - abs(n % (2 * m) - m)
        px[tri(k - 1, H - 1) * W + tri(k - 1, W - 1)] = _dim(level, 1, 3)
        px[tri(k, H - 1) * W + tri(k, W - 1)] = lv
    return _frame(px)
