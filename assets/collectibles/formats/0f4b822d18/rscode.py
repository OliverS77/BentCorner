"""Reed-Solomon-Fehlerkorrektur über GF(256) – wie beim QR-Code, für den Pixel-Code im Tauschticket.

encode(daten, nsym) hängt nsym Prüfbytes an; decode(block, nsym) repariert bis zu nsym/2 falsche Bytes und gibt
die Daten zurück (ValueError, wenn zu viel kaputt ist). Ein Block ist höchstens 255 Bytes lang.
"""
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(x, y):
    return 0 if x == 0 or y == 0 else _EXP[_LOG[x] + _LOG[y]]


def _div(x, y):
    return 0 if x == 0 else _EXP[(_LOG[x] + 255 - _LOG[y]) % 255]


def _pow(x, p):
    return _EXP[(_LOG[x] * p) % 255]


def _inv(x):
    return _EXP[255 - _LOG[x]]


def _p_scale(p, x):
    return [_mul(c, x) for c in p]


def _p_add(p, q):
    r = [0] * max(len(p), len(q))
    for i, c in enumerate(p):
        r[i + len(r) - len(p)] = c
    for i, c in enumerate(q):
        r[i + len(r) - len(q)] ^= c
    return r


def _p_mul(p, q):
    r = [0] * (len(p) + len(q) - 1)
    for j, b in enumerate(q):
        for i, a in enumerate(p):
            r[i + j] ^= _mul(a, b)
    return r


def _p_eval(p, x):
    y = p[0]
    for c in p[1:]:
        y = _mul(y, x) ^ c
    return y


def _p_div(dividend, divisor):
    out = list(dividend)
    for i in range(len(dividend) - (len(divisor) - 1)):
        c = out[i]
        if c:
            for j in range(1, len(divisor)):
                if divisor[j]:
                    out[i + j] ^= _mul(divisor[j], c)
    sep = -(len(divisor) - 1)
    return out[:sep], out[sep:]


_GEN = {}


def _generator(nsym):
    g = _GEN.get(nsym)
    if g is None:
        g = [1]
        for i in range(nsym):
            g = _p_mul(g, [1, _pow(2, i)])
        _GEN[nsym] = g
    return g


def encode(data, nsym):
    data = list(data)
    if len(data) + nsym > 255:
        raise ValueError("Block zu lang")
    _, rem = _p_div(data + [0] * nsym, _generator(nsym))
    return bytes(data + rem)


def _syndromes(msg, nsym):
    return [0] + [_p_eval(msg, _pow(2, i)) for i in range(nsym)]


def _error_locator(synd, nsym):
    loc, old = [1], [1]
    shift = len(synd) - nsym
    for i in range(nsym):
        k = i + shift
        delta = synd[k]
        for j in range(1, len(loc)):
            delta ^= _mul(loc[-(j + 1)], synd[k - j])
        old = old + [0]
        if delta:
            if len(old) > len(loc):
                new = _p_scale(old, delta)
                old = _p_scale(loc, _inv(delta))
                loc = new
            loc = _p_add(loc, _p_scale(old, delta))
    while loc and loc[0] == 0:
        del loc[0]
    if (len(loc) - 1) * 2 > nsym:
        raise ValueError("zu viele Fehler")
    return loc


def _error_positions(loc, n):
    pos = [n - 1 - i for i in range(n) if _p_eval(loc, _pow(2, i)) == 0]
    if len(pos) != len(loc) - 1:
        raise ValueError("Fehlerstellen nicht gefunden")
    return pos


def _correct(msg, synd, pos):
    coef = [len(msg) - 1 - p for p in pos]
    loc = [1]
    for c in coef:
        loc = _p_mul(loc, _p_add([1], [_pow(2, c), 0]))
    _, ev = _p_div(_p_mul(synd[::-1], loc), [1] + [0] * len(loc))
    ev = ev[::-1]
    xs = [_pow(2, -(255 - c)) for c in coef]
    err = [0] * len(msg)
    for i, xi in enumerate(xs):
        xi_inv = _inv(xi)
        prime = 1
        for j, xj in enumerate(xs):
            if j != i:
                prime = _mul(prime, 1 ^ _mul(xi_inv, xj))
        if prime == 0:
            raise ValueError("Fehlerwert nicht bestimmbar")
        y = _mul(xi, _p_eval(ev[::-1], xi_inv))
        err[pos[i]] = _div(y, prime)
    return _p_add(msg, err)


def decode(block, nsym):
    """-> Daten (bytes) ohne Prüfbytes; ValueError, wenn nicht zu retten."""
    msg = list(block)
    synd = _syndromes(msg, nsym)
    if max(synd) == 0:
        return bytes(msg[:-nsym])
    loc = _error_locator(synd, nsym)
    pos = _error_positions(loc[::-1], len(msg))
    msg = _correct(msg, synd, pos)
    if max(_syndromes(msg, nsym)) > 0:
        raise ValueError("nicht korrigierbar")
    return bytes(msg[:-nsym])
