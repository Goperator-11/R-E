"""손실 채널 모델과 FEC 블록 복구 실패 확률 계산.

핵심 아이디어
-------------
RS(N=K+r, K) 같은 MDS 부호는 N개 심볼 중 **r개까지의 소실을 정확히 복구**한다.
따라서 블록 복구 실패 확률은

    P_fail(K, r) = P[ 블록 안 소실 심볼 수 > r ]

로 딱 떨어진다. 문제는 "블록 안 소실 심볼 수"의 분포다.
실제 망의 손실은 독립적이지 않고 **뭉쳐서(burst)** 일어나므로,
독립 가정(이항분포)으로 계산하면 필요한 이중화를 과소평가한다.
그래서 Gilbert-Elliott 2상태 마르코프 모델을 쓰고, 소실 개수 분포를
동적계획법으로 **정확히** 구한다(근사·몬테카를로 아님).
"""

from __future__ import annotations

from dataclasses import dataclass, field


_CHANNEL_CACHE: dict = {}


def _mat_mul(a, b):
    return [
        [a[i][0] * b[0][j] + a[i][1] * b[1][j] for j in range(2)]
        for i in range(2)
    ]


def _mat_pow(m, n):
    result = [[1.0, 0.0], [0.0, 1.0]]
    base = [row[:] for row in m]
    while n > 0:
        if n & 1:
            result = _mat_mul(result, base)
        base = _mat_mul(base, base)
        n >>= 1
    return result


@dataclass
class GilbertElliott:
    """Gilbert-Elliott 손실 채널.

    상태 0 = Good(손실확률 p_good), 상태 1 = Bad(손실확률 p_bad).
    전이확률 q_gb = G->B, q_bg = B->G.

    from_burst(p, L)로 만들면 "평균 손실률 p, 평균 버스트 길이 L"이 된다.
    L=1이면 버스트 없음(단발 손실), L이 커질수록 뭉쳐서 터진다.
    """

    q_gb: float
    q_bg: float
    p_good: float = 0.0
    p_bad: float = 1.0
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_burst(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        """평균 손실률 p, 평균 버스트 길이 mean_burst인 채널을 만든다.

        단순 Gilbert(p_good=0, p_bad=1)에서
            평균 버스트 길이 = 1 / q_bg,
            정상상태 Bad 확률 pi_B = q_gb / (q_gb + q_bg) = p
        이므로 두 식을 풀면 아래가 된다.
        """
        p = min(max(p, 0.0), 0.999)
        if p <= 0.0:
            return cls(q_gb=0.0, q_bg=1.0)
        L = max(mean_burst, 1.0)

        # 🩸 (p, L)은 아무 조합이나 실현되지 않는다 (2026-08-18 독립 감사에서 발견).
        #
        # q_gb = p/(L(1-p)) 는 p > L/(1+L) 이면 **1을 넘는다.** 전이 확률이 1을
        # 넘으면 사슬이 무효가 되고, DP가 음수 확률과 발산값을 낸다:
        #     from_burst(0.60, 1.0) -> P_fail(32,8) = 8.195   (확률이 1 초과)
        #     from_burst(0.90, 2.0) -> P_fail(32,8) = -1.8e20
        #     from_burst(0.90, 1.0) -> P_fail(32,8) = -2.7e34
        # 더 나쁜 건 「포기 붕괴」 가드가 P_fail > 0.25 를 보는데 **음수면 발화하지
        # 않아** argmin 이 가장 음수인 J(=최대 r)를 고른다는 것이다.
        #
        # 도달 가능한 영역이다: p_safe = min(p_hat + z*se, 0.9) 라 상한이 0.9고,
        # 버스트가 안 잡히면(L=1) p_safe > 0.5 부터 무효다.
        #
        # 왜 실현이 안 되나: 단순 Gilbert(Good에서 무손실, Bad에서 전손실)에서
        # 손실률 p 를 만들려면 Good 구간과 Bad 구간의 길이비가 (1-p):p 여야 한다.
        # Bad 구간 평균이 L 이면 Good 구간 평균은 L(1-p)/p 인데, 이 값이 1보다
        # 작아지는 순간(= p > L/(1+L)) "평균 1패킷도 안 되는 정상 구간"을
        # 요구하는 셈이라 불가능하다.
        #
        # 처방: 손실률 p 를 지키고 **버스트를 p 가 요구하는 최소값으로 올린다.**
        # L_min = p/(1-p) 이면 q_gb 가 정확히 1이 된다. 손실률이 제어기의 결정에
        # 훨씬 크게 작용하므로 p 를 깎는 것보다 이쪽이 옳다. 그리고 이건 근사가
        # 아니라 사실의 보고다 - 손실률이 90%면 손실은 실제로 뭉쳐 있을 수밖에 없다.
        l_min = p / (1.0 - p)
        if L < l_min:
            L = l_min
        q_bg = 1.0 / L
        q_gb = min(p * q_bg / (1.0 - p), 1.0)
        return cls(q_gb=q_gb, q_bg=q_bg)

    @classmethod
    def for_prior(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        """**사전값(prior)으로 쓸 채널.** 버스트 정보가 없으면 독립 손실을 쓴다.

        🩸 H10 (2026-08-18 감사): `from_burst(p, 1.0)` 은 q_bg=1.0 이라 Bad 상태를
        매 심볼 빠져나간다 - 즉 **연속 손실이 원천적으로 불가능**한 채널이다.
        독립보다 오히려 음의 상관을 가진 특수한 채널이지 "버스트 없음"의
        중립 표현이 아니다. 그래서 전멸 확률 ft = pmf[n] 이 n>=2 에서 **정확히
        0**이 되고, 핸드셰이크 비용식의 PTO 항 전체가 0으로 곱해졌다
        (실측: p=5% 에서 from_burst 0.0 vs 독립 2.5e-3).

        버스트 추정이 없는 호출자가 받는 기본값이 바로 L=1 이므로, 그들은
        **전멸이 일어날 수 없는 모델**을 최적화하고 있었다 - 이 연구가 막으려는
        바로 그 실패 모드가 확률 0인 모델을.

        그래서 사전값 경로에서는 L<=1 이면 독립 손실(이항)을 쓴다. L>1 이면
        버스트가 실제로 추정된 것이므로 GE 를 그대로 쓴다.
        """
        # 2026-08-21 정정. 경계가 `<= 1.0` 이었는데 **iid 채널의 평균
        # 버스트는 1 이 아니라 1/(1-p)** 다. 그래서 1.0 < L < 1/(1-p)
        # 구간은 'iid 보다 덜 뭉친' 채널이 되고, 그건 H10 이 고치려던
        # 바로 그 병이 경계 오른쪽에서 재발한 것이다.
        # 실측(p=0.05, k=1, m=1): L=1.000 에서 p_fail=2.500e-3 인데
        # L=1.001 에서 4.995e-5 로 **50 배 낙관**이 됐다. 버스트가
        # 길어졌는데 모형이 좋아지는 것은 불가능하다.
        #
        # from_burst(p, 1/(1-p)) 는 **정확히 iid** 다:
        #   q_bg = 1-p, q_gb = p -> 정상분포 pi_bad = p, 손실률 p,
        #   P(손실|손실) = 1-q_bg = p.
        # 소거분포를 직접 대조한 최대차는 1e-16 수준이다.
        # 경계를 그리로 옮기면 P_fail 이 L 에 대해 연속이 되고,
        # L >= 1.1 구간의 값은 하나도 안 바뀐다.
        pc = min(max(p, 0.0), 0.999)
        if mean_burst <= 1.0 / (1.0 - pc):
            return cls.bernoulli(pc)
        return cls.from_burst(p, mean_burst)

    @classmethod
    def bernoulli(cls, p: float) -> "GilbertElliott":
        """독립 손실(이항분포) 채널. 비교용 기준선."""
        return cls(q_gb=0.5, q_bg=0.5, p_good=p, p_bad=p)

    @classmethod
    def cached(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        """추정치를 격자에 스냅해서 채널 객체(=DP 표)를 재사용한다.

        추정 손실률은 블록마다 미세하게 흔들리는데 그때마다 DP를 새로 돌리면
        낭비다. p는 0.01%, 버스트는 0.01 단위로 반올림해 표를 공유한다.
        이 정도 양자화는 r* 선택을 바꾸지 않는다(비용 차이가 격자보다 훨씬 큼).
        """
        key = (round(p * 1e4), round(mean_burst * 1e2))
        ch = _CHANNEL_CACHE.get(key)
        if ch is None:
            if len(_CHANNEL_CACHE) > 512:
                _CHANNEL_CACHE.clear()
            ch = cls.from_burst(key[0] / 1e4, key[1] / 1e2)
            _CHANNEL_CACHE[key] = ch
        return ch

    # ---- 기본 성질 -------------------------------------------------

    @property
    def transition(self):
        return [[1.0 - self.q_gb, self.q_gb], [self.q_bg, 1.0 - self.q_bg]]

    @property
    def stationary(self):
        total = self.q_gb + self.q_bg
        if total <= 0:
            return [1.0, 0.0]
        pi_bad = self.q_gb / total
        return [1.0 - pi_bad, pi_bad]

    @property
    def loss_rate(self) -> float:
        pi = self.stationary
        return pi[0] * self.p_good + pi[1] * self.p_bad

    @property
    def mean_burst(self) -> float:
        return 1.0 / self.q_bg if self.q_bg > 0 else float("inf")

    # ---- 블록 소실 개수 분포 (정확 계산) ---------------------------

    def pmf_table(self, n_max: int, interleave: int = 1):
        """길이 0..n_max 모든 블록에 대한 소실 개수 분포를 한 번에 계산.

        DP가 심볼을 하나씩 밀고 나가므로 n번째 단계의 상태가 곧 '길이 n인
        블록의 분포'다. 이중화 후보 r을 훑을 때 N=K+r이 매번 달라지는데,
        길이별로 DP를 새로 돌리면 같은 계산을 r_max번 반복하게 된다.
        한 번만 돌고 중간 결과를 전부 저장하면 그 낭비가 사라진다.

        interleave = 인터리빙 깊이 D. 한 블록의 심볼들이 D칸 간격으로
        띄엄띄엄 배치되면, 그 블록이 겪는 채널은 원래 마르코프 체인을
        D스텝마다 관측한 것과 같으므로 전이행렬 P^D를 쓰면 된다.
        (D를 키우면 버스트가 여러 블록으로 흩어져 각 블록엔 단발 손실처럼 보인다)
        """
        # 무효한 사슬은 **조용히 쓰레기를 내는 대신 즉시 실패**해야 한다.
        # from_burst() 는 이제 절대 무효값을 만들지 않지만, 생성자를 직접 쓰는
        # 경로가 있으므로 여기서 한 번 더 막는다.
        for name, v in (("q_gb", self.q_gb), ("q_bg", self.q_bg),
                        ("p_good", self.p_good), ("p_bad", self.p_bad)):
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    "GilbertElliott: %s=%r is not a probability - this chain "
                    "would make the DP produce negative/divergent values" 
                    % (name, v))

        key = (n_max, interleave)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        step = _mat_pow(self.transition, max(1, interleave))
        p00, p01 = step[0][0], step[0][1]
        p10, p11 = step[1][0], step[1][1]
        lg, lb = self.p_good, self.p_bad

        pi = self.stationary
        good = [pi[0]] + [0.0] * n_max     # good[c] = P(상태 G, 소실 c개)
        bad = [pi[1]] + [0.0] * n_max
        table = [[1.0]]

        for n in range(1, n_max + 1):
            ng = [0.0] * (n + 1)
            nb = [0.0] * (n + 1)
            for c in range(n):
                wg, wb = good[c], bad[c]
                if wg:
                    keep, lose = wg * (1.0 - lg), wg * lg
                    ng[c] += keep * p00
                    nb[c] += keep * p01
                    ng[c + 1] += lose * p00
                    nb[c + 1] += lose * p01
                if wb:
                    keep, lose = wb * (1.0 - lb), wb * lb
                    ng[c] += keep * p10
                    nb[c] += keep * p11
                    ng[c + 1] += lose * p10
                    nb[c + 1] += lose * p11
            good, bad = ng, nb
            table.append([good[c] + bad[c] for c in range(n + 1)])

        self._cache[key] = table
        return table

    def erasure_pmf(self, n_symbols: int, interleave: int = 1):
        """N개 심볼 중 정확히 i개가 소실될 확률 배열."""
        return self.pmf_table(n_symbols, interleave)[n_symbols]

    @staticmethod
    def _as_prob(x: float) -> float:
        """꼬리합은 부동소수점 누적 때문에 1을 1 ULP 넘길 수 있다
        (실측: 1.0000000000000002). 확률은 정의상 [0,1]이므로 여기서 고정한다.
        하류에서 `p_fail <= 1.0` 같은 비교를 하는 코드가 깨지지 않도록."""
        return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

    def p_fail(self, k: int, r: int, interleave: int = 1) -> float:
        """RS(K+r, K) 블록이 복구에 실패할 확률."""
        pmf = self.pmf_table(k + r, interleave)[k + r]
        return self._as_prob(sum(pmf[r + 1:]))

    def fail_curve(self, k: int, r_max: int, interleave: int = 1):
        """r = 0..r_max에 대한 P_fail 목록. DP 한 번으로 끝난다."""
        table = self.pmf_table(k + r_max, interleave)
        return [self._as_prob(sum(table[k + r][r + 1:]))
                for r in range(r_max + 1)]
