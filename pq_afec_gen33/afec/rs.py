from __future__ import annotations

_PRIM = 0x11D
_EXP = [0] * 512
_LOG = [0] * 256


def _build_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _PRIM
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_build_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("GF(256)에서 0의 역원은 없다")
    return _EXP[255 - _LOG[a]]


_MUL_TBL = [bytes(gf_mul(c, x) for x in range(256)) for c in range(256)]


def _mat_inverse(mat: list[list[int]]) -> list[list[int]]:
    n = len(mat)
    aug = [row[:] + [1 if i == j else 0 for j in range(n)]
           for i, row in enumerate(mat)]
    for col in range(n):
        pivot = next((r for r in range(col, n) if aug[r][col] != 0), None)
        if pivot is None:
            raise ValueError("특이행렬 - 이 소실 패턴은 복구 불가")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        inv_p = gf_inv(aug[col][col])
        aug[col] = [gf_mul(v, inv_p) for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col] != 0:
                f = aug[r][col]
                aug[r] = [x ^ gf_mul(f, y) for x, y in zip(aug[r], aug[col])]
    return [row[n:] for row in aug]


class RSErasureCode:
    def __init__(self, k: int, r: int):
        if type(k) is not int or type(r) is not int:
            raise TypeError("k and r must be integers")
        if k < 1 or r < 0:
            raise ValueError("k >= 1, r >= 0 이어야 한다")
        if k + r > 256:
            raise ValueError(f"K+r={k + r} > 256 - GF(256)으로는 불가")
        self.k = k
        self.r = r
        self.cauchy = [[1] * k] if r == 1 else [[gf_inv(i ^ (r + j)) for j in range(k)] for i in range(r)]

    @staticmethod
    def _combine(coeffs: list[int], symbols: list[bytes], size: int) -> bytes:
        acc = 0
        for c, sym in zip(coeffs, symbols):
            if c == 0:
                continue
            scaled = sym if c == 1 else sym.translate(_MUL_TBL[c])
            acc ^= int.from_bytes(scaled, "big")
        return acc.to_bytes(size, "big")

    def _row(self, index: int) -> list[int]:
        if index < self.k:
            return [1 if j == index else 0 for j in range(self.k)]
        return self.cauchy[index - self.k]

    def encode(self, source: list[bytes]) -> list[bytes]:
        if len(source) != self.k:
            raise ValueError(f"원본 심볼 {self.k}개가 필요하다 (받은 것: {len(source)})")
        size = len(source[0])
        if any(len(s) != size for s in source):
            raise ValueError("심볼 길이가 모두 같아야 한다")
        return [self._combine(self.cauchy[i], source, size) for i in range(self.r)]

    def decode(self, received: dict[int, bytes]) -> list[bytes]:
        if any(type(i) is not int or not 0 <= i < self.k + self.r
               for i in received):
            raise ValueError("received symbol index is outside the codeword")
        if len(received) < self.k:
            raise ValueError(
                f"살아남은 심볼 {len(received)}개 < K={self.k} - 복구 불가")

        size = len(next(iter(received.values())))
        if any(len(s) != size for s in received.values()):
            raise ValueError("received symbols must have equal lengths")
        indices = sorted(received)[:self.k]

        if indices == list(range(self.k)):
            return [received[i] for i in range(self.k)]

        m = [self._row(t) for t in indices]
        m_inv = _mat_inverse(m)
        symbols = [received[t] for t in indices]
        return [self._combine(m_inv[j], symbols, size) for j in range(self.k)]
