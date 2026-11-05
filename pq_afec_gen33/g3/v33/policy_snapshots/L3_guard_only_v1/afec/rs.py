"""GF(256) 위의 Reed-Solomon 소실정정 부호 (systematic, Cauchy 행렬).

왜 이게 필요한가
----------------
시뮬레이터와 비용식은 전부 **"MDS 부호는 N개 중 r개까지의 소실을 정확히 복구한다"**는
가정 위에 서 있다. 이 가정이 틀리면 `P_fail` 계산도, 그걸로 고른 r*도 전부 무의미하다.
그런데 지금까지는 그 가정을 코드로 확인한 적이 없다. 실제 부호기를 만들어
**임의의 r개 소실이 정말 복구되는지, r+1개면 정말 실패하는지**를 검증한다.

왜 Cauchy 행렬인가
------------------
소실정정용 생성행렬은 **모든 정사각 부분행렬이 가역**이어야 임의의 소실 패턴을
복구할 수 있다(=MDS). 반데르몬드 행렬을 systematic 형태로 행축약하면 이 성질이
깨질 수 있는 반면, **Cauchy 행렬은 구성상 항상 MDS**다.

    C[i][j] = 1 / (x_i + y_j),   {x_i} 와 {y_j} 는 서로소인 원소 집합

GF(2^8)에서 덧셈은 XOR이므로 `x_i ^ y_j`가 0이 아니기만 하면 된다.
x_i = 0..r-1, y_j = r..r+k-1 로 잡으면 두 집합이 겹치지 않아 조건이 자동 만족된다.

속도
----
심볼 하나를 상수배 하는 연산은 256바이트 룩업표 + `bytes.translate`로 처리하고,
누산은 **big int XOR**로 한다. 파이썬 바이트 루프 대신 C 레벨에서 돌아 실용 속도가 나온다.
"""

from __future__ import annotations

# GF(2^8), 기약다항식 0x11D
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


# c배 룩업표 256개 (64KB). bytes.translate로 심볼 전체를 한 번에 상수배 한다.
_MUL_TBL = [bytes(gf_mul(c, x) for x in range(256)) for c in range(256)]


def _mat_inverse(mat: list[list[int]]) -> list[list[int]]:
    """GF(256) 정사각행렬의 역행렬. 가우스 소거."""
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
    """RS(K+r, K) systematic 소실정정 부호.

    심볼 인덱스 0..K-1 = 원본, K..K+r-1 = 이중화 심볼.
    """

    def __init__(self, k: int, r: int):
        if type(k) is not int or type(r) is not int:
            raise TypeError("k and r must be integers")
        if k < 1 or r < 0:
            raise ValueError("k >= 1, r >= 0 이어야 한다")
        if k + r > 256:
            raise ValueError(f"K+r={k + r} > 256 - GF(256)으로는 불가")
        self.k = k
        self.r = r
        # Cauchy 행렬: x_i = i (0..r-1), y_j = r+j (r..r+k-1) -> 두 집합이 서로소
        self.cauchy = [[gf_inv(i ^ (r + j)) for j in range(k)] for i in range(r)]

    # ---- 내부 헬퍼 -------------------------------------------------

    @staticmethod
    def _combine(coeffs: list[int], symbols: list[bytes], size: int) -> bytes:
        """Σ coeffs[j]·symbols[j] 를 big int XOR로 누산."""
        acc = 0
        for c, sym in zip(coeffs, symbols):
            if c == 0:
                continue
            scaled = sym if c == 1 else sym.translate(_MUL_TBL[c])
            acc ^= int.from_bytes(scaled, "big")
        return acc.to_bytes(size, "big")

    def _row(self, index: int) -> list[int]:
        """생성행렬 [I; C]의 index번째 행."""
        if index < self.k:
            return [1 if j == index else 0 for j in range(self.k)]
        return self.cauchy[index - self.k]

    # ---- 공개 API --------------------------------------------------

    def encode(self, source: list[bytes]) -> list[bytes]:
        """원본 심볼 K개 -> 이중화 심볼 r개."""
        if len(source) != self.k:
            raise ValueError(f"원본 심볼 {self.k}개가 필요하다 (받은 것: {len(source)})")
        size = len(source[0])
        if any(len(s) != size for s in source):
            raise ValueError("심볼 길이가 모두 같아야 한다")
        return [self._combine(self.cauchy[i], source, size) for i in range(self.r)]

    def decode(self, received: dict[int, bytes]) -> list[bytes]:
        """살아남은 심볼 {인덱스: 데이터} -> 원본 K개 복원.

        살아남은 게 K개 미만이면 ValueError. 이게 곧 '복구 실패'다.
        """
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

        # 원본이 전부 살아있으면 복호 자체가 불필요
        if indices == list(range(self.k)):
            return [received[i] for i in range(self.k)]

        m = [self._row(t) for t in indices]
        m_inv = _mat_inverse(m)
        symbols = [received[t] for t in indices]
        return [self._combine(m_inv[j], symbols, size) for j in range(self.k)]
