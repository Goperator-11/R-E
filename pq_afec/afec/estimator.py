"""망 상태 추정기 - 손실률, 버스트 길이, 그리고 '이 손실이 혼잡 때문인가'.

FEC 제어기가 알아야 하는 건 손실률 하나가 아니다. 세 가지다.

1. 손실률 p       : 얼마나 잃는가
2. 버스트 길이 L  : 어떻게 잃는가 (뭉쳐서 잃으면 같은 p라도 이중화가 더 필요)
3. 혼잡 확신도 g  : 왜 잃는가  <-- 이게 제일 중요하다

3번이 필요한 이유: 손실 원인이 **혼잡**이면 FEC를 늘리는 건 불난 데 기름이다.
큐에 더 많은 패킷을 밀어넣어 손실을 더 만들고, 정작 유용한 데이터를 밀어낸다.
반대로 원인이 **링크 오류/무선 간섭**이면 재전송보다 FEC가 정답이다.
둘을 구분하는 신호는 RTT다. 큐가 차서 잃는 손실은 항상 RTT 상승을 동반하지만,
링크 오류는 RTT를 건드리지 않는다. ECN CE 마킹이 오면 혼잡이 확정이다.
"""

from __future__ import annotations

import math


class LossEstimator:
    """손실률 + 버스트 길이 추정.

    설계 판단 하나를 명시해 둔다. 초안에서는 '올릴 땐 빠르게(alpha=0.3),
    내릴 땐 느리게' 하는 비대칭 EWMA를 썼는데, **안전마진을 세 군데서
    중복으로 얹는 결과**가 됐다.
      (1) 추정기의 비대칭 상승
      (2) 신뢰상한 p_safe
      (3) 비용식의 T_recover (저보호를 이미 강하게 벌함)
    그래서 oracle 대비 이중화를 1.5~2배 과하게 썼다. 위험 반영은 (3)이
    담당해야 할 몫이므로, 추정기는 **편향 없이 추정하고 불확실성만 보고**하도록
    바꿨다. 급변에 대한 반응은 평활 상수 대신 **변화 감지**로 따로 처리한다.

    손실률은 비율의 EWMA가 아니라 (손실 수 EWMA)/(전송 수 EWMA)로 구한다.
    블록 크기가 바뀌어도 가중이 흐트러지지 않는다.
    """

    def __init__(self, alpha=0.08, p_init=0.01, z=1.0,
                 jump_alpha=0.40, surprise_threshold=0.10, jump_min_losses=2,
                 jump_confirm=2, prior_weight=100.0, burst_init=1.0,
                 down_h=3.0):
        self.alpha = alpha
        self.z = z                       # 신뢰상한 계수 (0=평균만 사용)
        self.jump_alpha = jump_alpha     # 급변 감지 시 쓸 큰 평활 상수
        self.surprise_threshold = surprise_threshold
        self.jump_min_losses = jump_min_losses
        self.jump_confirm = jump_confirm  # 연속 몇 블록 놀라워야 급변으로 인정할지

        # 사전분포의 증거 가중치(심볼 수 상당). v0.1에서는 100으로 하드코딩돼
        # 있었는데, 목적지별 통계 캐시(v0.2)가 이 값을 조절한다.
        #
        # ⚠️ w는 **불확실성(n_eff -> se)에만** 작용한다. EWMA 질량(_sent)에
        # 넣으면 추정치의 관성이 캐시 신뢰에 비례해져서, 캐시가 틀렸을 때
        # 추적 속도가 w배로 느려진다(실측: 틀린-낮음 캐시 후회가 w=100에서
        # 33.5%, w=1536에서 44.8% - 급변 검정이 버스트 잡음에 끊긴 시드가
        # 꼬리를 만든다). 추적 속도는 채널 추적의 문제지 캐시 신뢰의 문제가
        # 아니다. 그래서 트래커 질량 시드는 v0.1 값(100)에 고정하고, 사전값은
        # **시작점(p_init)과 확신도(n_eff)만** 준다. "추정기는 편향 없이
        # 추정하고 위험은 비용식이 담당한다"(v0.1 §7)와 같은 분리 원칙이다.
        self._prior_weight = max(float(prior_weight), 1.0)
        # 🩸 E2 (2026-08-18 감사): 여기가 `seed_mass = min(prior_weight, 100)`
        # 이었다. 100 미만에서 prior_weight 를 그대로 따라가므로 **EWMA 질량이
        # 캐시 신뢰도에 비례**했다 - 바로 위 주석이 "그러면 안 된다"고 적어둔
        # 그것이다. 캐시 항목이 낡을수록 lookup 이 낮은 weight 를 주므로, 같은
        # 채널·같은 시드인데 추적 속도가 캐시 나이에 따라 달라졌다
        # (실측: 4블록 후 p_hat 이 w=100 에서 0.0667, w=30 에서 0.0795 - 78% 차).
        # 추적 관성은 채널 추적의 문제지 캐시 신뢰의 문제가 아니므로 상수로 못박는다.
        seed_mass = 100.0
        self._sent = seed_mass
        self._lost = p_init * seed_mass
        self._observed = 0.0             # 실제로 관측한 심볼 누적 수 (n_eff 계산용)
        self._run_sum = max(float(burst_init), 1.0)  # 끝난 손실 구간 길이 합 (EWMA)
        self._run_num = 1.0              # 끝난 손실 구간 개수 (EWMA)
        # 🩸 E1 (2026-08-18 감사): 사전 버스트는 **관측으로 지워지지 않는 값**이었다.
        # 버스트 EWMA 는 '끝난 손실 구간'이 있는 블록에서만 갱신되는데(의도된
        # 설계), 링크가 깨끗해지면 그런 블록이 아예 안 생긴다. 게다가 급변
        # 리셋도 _run_sum/_run_num 을 안 건드렸다. 그래서 낡은 버스트 6.0 이
        # 무손실 300블록(19,200심볼) 뒤에도 그대로 남아 se 팽창
        # sqrt(2L(1-p)-1)=3.3배를 영구히 곱했다 (실측: 깨끗한 링크에서 r=6 vs 2).
        # z=1.5 재튜닝이 막으려던 ghost 시나리오의 **나머지 절반**이다.
        # 처방: 실제로 관측한 손실 구간 수를 세고, 증거가 하나도 없이 심볼만
        # 쌓이면 사전 버스트를 중립값(1.0)으로 되돌린다. 손실을 본 적이 없는데
        # "이 경로는 뭉쳐서 잃는다"고 계속 주장할 근거가 없다.
        self._runs_observed = 0          # 실제로 관측한 '끝난 손실 구간' 수
        self._burst_prior_fade = 2000.0  # 이 심볼 수만큼 무증거면 사전값 소멸
        self.down_h = down_h             # 하향 SPRT 발화 문턱 (로그우도비)
        self.jump_boost_blocks = 4       # 급변 확정 후 몇 블록에 jump_alpha를 줄지
        self.jumped = False
        self._streak = 0
        self._open_run = 0               # 블록 경계에 걸쳐 진행 중인 손실 구간
        self._down_llr = 0.0             # 하향 변화 누적 로그우도비 (CUSUM)
        self._boost_left = 0             # 남은 부스트 블록 수

    @property
    def p(self) -> float:
        return self._lost / self._sent if self._sent else 0.0

    @property
    def burst(self) -> float:
        """평균 버스트 길이 = (구간 길이 합) / (구간 개수).

        관측된 손실 구간이 하나도 없으면(= 사전값만 남아 있으면) 증거가 쌓일수록
        중립값 1.0 으로 되돌린다 - E1 참고. 손실 구간을 한 번이라도 보면 EWMA 가
        정상적으로 사전값을 밀어내므로 이 보정은 꺼진다.

        블록별 평균을 EWMA 하면 안 된다. 구간이 1개뿐인 블록과 3개인 블록이
        같은 가중을 받아 **짧은 구간에 과대 가중**된다. 손실률에서 비율의
        EWMA 대신 개수의 비를 쓴 것과 정확히 같은 이유다.
        (다만 실측으로는 이 수정만으로 3.52 -> 3.53 밖에 안 움직였다.
         남은 편향의 주범은 따로 있었다 - observe_mask의 ⚠️ 주석 참고.)
        """
        raw = self._run_sum / self._run_num if self._run_num else 1.0
        if self._runs_observed == 0 and self._observed > 0.0:
            w = min(self._observed / self._burst_prior_fade, 1.0)
            return raw * (1.0 - w) + 1.0 * w
        return raw

    @burst.setter
    def burst(self, value: float) -> None:
        self._run_sum, self._run_num = float(value), 1.0
        self._runs_observed = 0

    def observe_mask(self, mask: list[bool]) -> None:
        """블록 하나의 손실 마스크를 반영 (True = 손실).

        블록 단위로 끊어서 세지 않고 **손실 구간을 블록 경계 너머로 이어 붙인다.**
        블록마다 독립적으로 세면 경계를 걸친 버스트가 둘로 쪼개져 평균 버스트
        길이가 짧게 나온다. 실측 편향이 −15%였다(참값 4.0 -> 추정 3.42).
        패킷 번호 공간에서 블록은 실제로 연속이므로 이어 붙이는 쪽이 맞다.
        """
        n_symbols = len(mask)
        n_lost = sum(mask)

        if self._is_surprising(n_symbols, n_lost):
            self._streak += 1
        else:
            self._streak = 0
        was_jumped = self.jumped
        self.jumped = self._streak >= self.jump_confirm

        # ⚠️ jump_alpha는 **급변을 확정시킨 블록이 아니라 그 다음 블록들**에
        # 준다 (v0.2.1 수정 - 실측 상방 편향 +10%의 범인).
        #
        # 놀라운 블록에 큰 α를 주는 것은 관측치를 자기 자신의 극단성으로
        # 가중하는 것이다. 위쪽 오탐은 항상 손실 많은 블록에서 나므로, 오탐률
        # 1~3%에 5배 가중이 곱해져 추정이 위로만 표류했다(p=5%·L=4에서
        # +10.9%, 부스트를 끄면 +0.4%). "추정기는 편향 없이"(§7 원칙)를 급변
        # 메커니즘이 세 번째로 어긴 사례다.
        # 확정 **이후** 블록들은 새 국면의 공정한 표본이라, 여기에만 부스트를
        # 주면 진짜 급변은 그대로 빠르게 따라잡고(새 국면 표본이 5배 가중),
        # 오탐이면 평범한 블록에 가중이 갈 뿐이라 편향이 생기지 않는다.
        if self._boost_left > 0:
            a = self.jump_alpha
            self._boost_left -= 1
        else:
            a = self.alpha

        self._lost = (1.0 - a) * self._lost + a * n_lost
        self._sent = (1.0 - a) * self._sent + a * n_symbols
        self._observed += n_symbols
        if self.jumped and not was_jumped:
            # 국면이 바뀌었으면 이전 증거는 더 이상 이 국면을 말해주지 않는다.
            # 증거를 리셋해야 se가 다시 커져 제어기가 조심스러워진다.
            # **사전값(캐시)도 같이 무효화한다** - 국면이 바뀌었다는 판정은
            # 캐시가 물려준 사전값이 지금 채널을 설명하지 못한다는 뜻이기도 하다.
            # 이걸 안 지우면 큰 prior_weight가 n_eff를 계속 부풀려 se가 작게
            # 나오고, 틀린 캐시에서 벗어난 뒤에도 근거 없이 자신만만해진다.
            #
            # ⚠️ 리셋은 **급변이 확정되는 순간 한 번만** 한다 (v0.2.1 수정).
            # jumped가 여러 블록 이어질 때 매 블록 리셋하면 새 국면에서 쌓이는
            # 증거까지 계속 지워, 국면 전환이 긴 경우 n_eff가 블록 하나
            # 크기에 눌러붙는다.
            self._observed = float(n_symbols)
            self._prior_weight = 0.0
            # 국면이 바뀌었으면 **버스트 사전값도** 이 국면을 설명하지 못한다.
            # E1 이전에는 p 쪽만 무효화하고 버스트는 그대로 남겨, 캐시가 물려준
            # 버스트가 급변 뒤에도 se 를 계속 부풀렸다.
            if self._runs_observed == 0:
                self._run_sum, self._run_num = 1.0, 1.0
            self._down_llr = 0.0         # 새 국면 기준으로 다시 쌓는다
            self._boost_left = self.jump_boost_blocks
            # **EWMA 질량도 새 국면 규모로 줄인다** (v0.2 스윕에서 잡힌 결함).
            # prior_weight만 지우면 불확실성 장부는 정리되지만 추정치의 분모
            # (_sent)에 사전 질량이 그대로 남는다. 캐시가 w=1536을 물려줬다면
            # jump_alpha=0.40이 설계 속도(2~3블록)가 아니라 7~8블록에 걸쳐
            # 수렴하고, 그 사이 블록이 전부 실패한다. 실측: 틀린-낮음 캐시
            # 시나리오의 후회가 w=100에서 33.9%, w=1536에서 49.0%로 벌어졌다.
            # 비율(추정치)은 보존하고 질량만 블록 하나 규모로 줄이면, 이후
            # 갱신은 w와 무관하게 설계된 속도로 움직인다. v0.1 영역(w=100,
            # 블록 64)에서는 질량이 이미 그 규모라 사실상 무변화다.
            if self._sent > n_symbols > 0:
                f = n_symbols / self._sent
                self._sent *= f
                self._lost *= f

        # 이전 블록에서 이어진 구간부터 시작해 끝난 구간만 집계한다
        closed: list[int] = []
        run = self._open_run
        for lost in mask:
            if lost:
                run += 1
            elif run:
                closed.append(run)
                run = 0
        self._open_run = run             # 아직 안 끝난 구간은 다음 블록으로 넘긴다

        if closed:
            b = 0.15
            self._run_sum = (1.0 - b) * self._run_sum + b * sum(closed)
            self._run_num = (1.0 - b) * self._run_num + b * len(closed)
            self._runs_observed += len(closed)
        # ⚠️ 무손실 블록에서 버스트를 1 쪽으로 당기지 않는다.
        #    예전엔 당겼는데, 손실 5%·버스트 4인 채널도 무손실 블록이 30~40%라
        #    매번 아래로 끌려 추정이 계속 −12% 낮게 나왔다. 무손실 블록은
        #    버스트 길이에 대한 정보가 **없는** 것이지 '버스트가 1'이라는
        #    증거가 아니다. 게다가 손실이 없으면 P_fail이 어차피 0에 가까워
        #    버스트 값이 r 결정에 영향을 주지도 않는다.


    def _is_surprising(self, n_symbols: int, n_lost: int) -> bool:
        """이 관측이 현재 모델로 설명되는가? (위: 블록 단위 / 아래: 누적 증거)

        기준은 '많이 잃었는가'가 아니라 **'지금 모델이 예측하는 것보다 많이/적게
        잃었는가'** 다. 블록 소실 개수의 정확한 분포를 이미 갖고 있으므로
        공짜로 얻어지는 판정이다. 위쪽과 아래쪽의 **메커니즘이 다른 데는
        이유가 있다** (2026-08-14, v0.2.1):

        - **위쪽(손실 급증)은 블록 하나로 판정한다.** 손실 스파이크는 시끄러운
          증거라 단일 블록 꼬리확률로 충분하고, 보호가 급한 쪽이라 빨라야 한다.
        - **아래쪽(손실 급감)은 블록 하나로 판정할 수 없다.** 소실 개수 분포는
          바닥이 0에 붙은 오른쪽 꼬리 분포라, 최선의 관측(무손실 블록)조차
          하단 꼬리확률이 크다(p=2%·L=4 모델에서 P[무손실] = 0.69). 즉 단일
          블록 하단 검정은 웬만한 하향 변화에 **원리적으로 실명**이다.
          v0.1이 하단 검정을 넣고도 +10% 상방 편향이 남았던 이유다: 위쪽
          오탐(스파이크 추격)은 계속 걸리는데 아래쪽 교정은 안 걸려서,
          jump_alpha가 오른쪽 꼬리만 편식했다.
          그래서 아래쪽은 **누적 로그우도비(SPRT/CUSUM)**로 판정한다:
              llr_t = log P(관측 | p̂/2, L̂) − log P(관측 | p̂, L̂)
              S_t = max(0, S_{t-1} + llr_t),   S_t > down_h 이면 하향 급변
          모델이 맞으면 E[llr] < 0이라 S는 0 근처에 붙어 있고(오탐 억제),
          모델이 실제보다 높으면 llr > 0이 쌓여 몇 블록 안에 문턱을 넘는다.
          위는 민감하게(보호 우선), 아래는 증거를 쌓아 교정(낭비 회수) -
          메커니즘은 비대칭이지만 장기 정확도는 대칭이 되는 구조다.
        """
        from .channel import GilbertElliott
        pmf = GilbertElliott.cached(self.p, self.burst_safe).erasure_pmf(n_symbols)

        # 🩸 E4 (2026-08-18 감사): 예전엔 위쪽 검정이 먼저 `return True` 를 했다.
        # 그런데 하단 CUSUM 이 0 근처에 붙어 있으려면 **음수 llr** 이 계속
        # 들어와야 하고, 그 음수 llr 은 정확히 '손실이 많은 블록'에서 나온다 -
        # 즉 위쪽 검정이 걸러내던 바로 그 블록들이다. 결과적으로 CUSUM 은
        # 무손실 블록의 양수 기여만 먹고 음수 기여를 빼먹어 위로 표류했다
        # (실측: 정상 채널 2000블록 중 371개(18.6%)에서 갱신이 생략).
        # 그래서 **누적을 먼저 하고 판정을 나중에** 한다.
        pmf_half = GilbertElliott.cached(self.p / 2.0,
                                         self.burst_safe).erasure_pmf(n_symbols)
        c = min(n_lost, n_symbols)
        llr = math.log(max(pmf_half[c], 1e-300)) - math.log(max(pmf[c], 1e-300))
        self._down_llr = max(0.0, self._down_llr + llr)

        # 위쪽: 예상보다 많이 잃었나 (잡음 방지로 최소 손실 개수 요구)
        if n_lost >= self.jump_min_losses:
            if sum(pmf[min(n_lost, n_symbols):]) < self.surprise_threshold:
                return True

        return self._down_llr > self.down_h

    @property
    def n_eff(self) -> float:
        """지금까지 쌓인 증거의 양(심볼 수).

        ⚠️ **EWMA 창 크기만 쓰면 안 된다** (2026-08-13에 잡힌 결함).
        `_sent x (2-a)/a`는 창 길이라 **첫 블록부터 상수**다(약 1536).
        심볼 64개만 봤는데 1536개를 본 것처럼 주장하니 콜드 스타트에서
        불확실성이 0에 가깝게 나오고, 제어기가 근거 없이 자신만만해진다.

        증상은 z 튜닝에서 드러났다. **짧은 연결(30블록)은 z=3.0을, 긴 연결
        (400블록)은 z=0.0을 최적이라 답했다.** 하나의 z로 둘 다 못 잡는 게 아니라,
        n_eff가 증거량을 반영하지 않아 z가 그 역할을 대신 떠맡고 있었던 것이다.

        실제 관측량으로 상한을 씌우면 연결 초반엔 se가 크고(조심), 증거가
        쌓이면 창 크기로 수렴한다(효율). 이게 원래 의도한 동작이다.

        상관 보정은 se에서 따로 한다.
        """
        window = self._sent * (2.0 - self.alpha) / self.alpha
        return max(min(window, self._observed + self._prior_weight), 1.0)

    def snapshot(self) -> tuple[float, float, float]:
        """캐시에 저장할 (p, burst, 증거량). 연결이 끝날 때 호출한다.

        증거량은 **직접 관측한 심볼 수만** 센다. 물려받은 사전값의 가중치를
        더해서 저장하면 캐시를 거칠 때마다 증거가 눈덩이처럼 불어나
        (사전 400 -> 저장 400+관측 -> 다음 사전 더 큼 -> ...) 실제보다
        훨씬 확신에 찬 캐시가 된다. 상한은 EWMA 창 크기 - 추정기가 기억하지
        못하는 양을 캐시가 기억한다고 주장할 수 없다.
        """
        window = self._sent * (2.0 - self.alpha) / self.alpha
        return self.p, self.burst_safe, min(self._observed, window)

    @property
    def se(self) -> float:
        """손실률 추정의 표준오차 - **버스트 상관을 보정한** 값.

        이항 표준오차 sqrt(p(1-p)/n)은 표본이 **독립일 때만** 맞다.
        버스트 채널의 손실은 강하게 상관돼 있어서 실제 분산이 훨씬 크다.
        보정 없이 쓰면 **버스트가 심할수록 불확실성을 과소평가**하는데,
        하필 그때가 보호가 가장 필요한 순간이다.

        Gilbert 사슬의 지연-1 자기상관은 rho = 1 - 1/(L(1-p)) 이고,
        상관 있는 표본 평균의 분산 팽창 계수는 (1+rho)/(1-rho) = 2L(1-p) - 1 이다.
        L=1이면 계수가 1이 되어 이항 공식으로 자연히 되돌아간다.
        """
        p = self.p
        L = self.burst_safe
        inflation = max(2.0 * L * (1.0 - p) - 1.0, 1.0)
        return math.sqrt(max(p * (1.0 - p), 1e-9) / self.n_eff * inflation)

    @property
    def p_safe(self) -> float:
        """제어기가 실제로 쓸 손실률 = 평균이 아니라 신뢰상한.

        표본이 적을 때(연결 초반) 평균만 믿으면 운 좋게 무손실이었다는
        이유로 보호를 0으로 내려버린다. 추정 오차만큼만 얹어서 쓴다.
        """
        return min(self.p + self.z * self.se, 0.9)

    @property
    def burst_safe(self) -> float:
        return max(self.burst, 1.0)


class CongestionDetector:
    """RTT 팽창 + ECN으로 '혼잡 확신도' g in [0,1]을 만든다.

    g=0 : 큐가 비어 있는데 손실이 난다 -> 링크 오류. FEC가 정답.
    g=1 : 큐가 부풀었거나 CE 마킹 -> 혼잡. FEC를 늘리면 안 된다.
    """

    def __init__(self, theta_lo=0.10, theta_hi=0.50, ecn_decay=0.8,
                 rtt_min_window=200):
        self.theta_lo = theta_lo
        self.theta_hi = theta_hi
        self.ecn_decay = ecn_decay
        self.rtt_min_window = rtt_min_window
        self.srtt = None
        self._ecn = 0.0
        # rtt_min은 **창 안의 최솟값**이다. 아래 rtt_min 프로퍼티 주석 참고.
        self._cur_min = None
        self._prev_min = None
        self._count = 0

    def observe_rtt(self, rtt_ms: float) -> None:
        self.srtt = rtt_ms if self.srtt is None else 0.875 * self.srtt + 0.125 * rtt_ms

        self._cur_min = rtt_ms if self._cur_min is None else min(self._cur_min, rtt_ms)
        self._count += 1
        if self._count >= self.rtt_min_window:
            self._prev_min, self._cur_min, self._count = self._cur_min, None, 0

    @property
    def rtt_min(self):
        """최근 창 안의 최소 RTT.

        ⚠️ **단조 감소하는 전역 최솟값을 쓰면 안 된다.** 경로가 바뀌거나 기지국이
        바뀌어 기저 RTT가 영구히 올라가면, 옛 최솟값이 계속 남아 팽창률이
        항상 높게 잡힌다. 그러면 혼잡 확신도 g가 1에 붙박이고 **FEC가 영원히
        억제된다** - 링크 오류로 손실이 나도 이중화를 안 늘리게 된다.
        창을 두 개(현재/직전) 굴려 O(1)로 최근 창의 최솟값을 유지한다.
        """
        mins = [m for m in (self._cur_min, self._prev_min) if m is not None]
        return min(mins) if mins else None

    def observe_ecn(self, ce_marked: bool) -> None:
        self._ecn = self.ecn_decay * self._ecn + (1.0 - self.ecn_decay) * (1.0 if ce_marked else 0.0)

    @property
    def inflation(self) -> float:
        """RTT 팽창률 = (평활 RTT - 최소 RTT) / 최소 RTT. 큐 지연의 대리 지표."""
        if self.srtt is None or not self.rtt_min:
            return 0.0
        return max(0.0, (self.srtt - self.rtt_min) / self.rtt_min)

    @property
    def g(self) -> float:
        infl = self.inflation
        span = max(self.theta_hi - self.theta_lo, 1e-6)
        from_rtt = min(max((infl - self.theta_lo) / span, 0.0), 1.0)
        return max(from_rtt, min(self._ecn * 2.0, 1.0))
