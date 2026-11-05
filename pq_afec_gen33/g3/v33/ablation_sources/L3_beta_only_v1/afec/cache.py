"""목적지별 통계 캐시 - 연결 사이로 (손실률, 버스트) 추정치를 물려준다.

왜 필요한가 (v0.1 실측)
-----------------------
짧은 연결(30블록)은 1 RTT 피드백 지연 때문에 학습할 시간 자체가 없다.
콜드 스타트 적응형의 최악 후회 30.0%는 정적 FEC(27.1%)보다도 나빴고,
완벽한 사전값을 주면 9.8%까지 내려갔다. 해법은 파라미터 튜닝이 아니라
**직전 연결이 배운 것을 다음 연결에 물려주는 것**이다.

이 캐시는 두 소비자를 한 저장소로 섬긴다.
  1. 핸드셰이크 shield() - 패킷이 하나도 오가기 전에 p_prior가 필요하다.
  2. 데이터 구간 제어기 - LossEstimator의 워밍 스타트.

키 설계: (접속망 ID, 목적지 /24) 복합키
----------------------------------------
캐시하는 통계는 "경로의 손실 특성"이다. 손실은 대부분 접속망(라스트마일:
Wi-Fi 간섭, 셀룰러 전파 상태)에서 나므로, **접속망이 키의 절반**이다.

- 접속망 ID: Wi-Fi는 BSSID, 셀룰러는 PLMN(사업자망 ID), 유선은 인터페이스.
  시뮬레이터/테스트에서는 불투명 문자열이면 된다.
- 목적지: IPv4는 /24, IPv6는 /48 프리픽스. 같은 데이터센터/PoP로 가는
  경로는 프리픽스 단위로 묶인다.
- **SNI는 키로 쓰지 않는다.** SNI는 서버의 이름이지 경로가 아니다. CDN은
  같은 이름이 PoP마다 다른 경로로 가고, IP가 바뀌면 경로 통계는 이전되지
  않는다. 게다가 SNI 키는 캐시를 방문 기록으로 만들어 프라이버시 부담만
  키운다(이 캐시는 그 자체로 브라우저의 TCP metrics 캐시와 같은 성격의
  잔존물이므로, 실장 시 메모리 상주 + 짧은 TTL이 맞다).

이동(Wi-Fi <-> 셀룰러) 무효화는 **키 설계가 공짜로 해결한다**: 접속망이
바뀌면 키가 달라져서 옛 항목을 아예 읽지 않는다. 이벤트 감지나 purge
로직이 필요 없고, 같은 망으로 돌아오면 그 망의 통계가 그대로 살아 있다.

폴백 사다리: (망, /24) 정확 항목 -> (망, *) 망 집계 -> 기본값.
같은 망에서 처음 가는 목적지도 망 집계의 덕을 본다 - 손실의 주범이
접속망이라는 가정의 직접적 배당이다.

사전값은 점추정이 아니라 증거 가중치와 함께 넘긴다
--------------------------------------------------
lookup()이 돌려주는 것은 (p, burst, weight)다. weight는 "이 사전값이
관측 몇 심볼어치의 발언권을 갖는가"이고, LossEstimator의 prior_weight로
들어간다. **이 값이 캐시가 틀렸을 때의 회복 속도를 직접 결정한다**:
크면 워밍 효과가 크지만 틀린 값이 오래 남고, 작으면 반대다.

- 저장 시 증거 상한 w_cap = 추정기 EWMA 창(~1536심볼). 추정기가 기억하지
  못하는 양을 캐시가 기억한다고 주장할 수 없다.
- 나이 감쇠: weight를 반감기 half_life_s로 지수 감쇠. 오래된 항목은
  점추정은 남되 발언권이 준다. w_min 밑으로 떨어지면 없는 항목으로 친다.
- 병합은 유사-베이지안 가중 평균: 관측 몇 번으로 채워지는 짧은 연결들이
  여러 번 반복되면 증거가 누적된다 - 정확히 짧은 연결 시나리오가 캐시를
  기르는 구조다.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Prior:
    """추정기/shield에 넘길 사전값. weight=0이면 순수 기본값."""
    p: float
    burst: float
    weight: float
    source: str          # 'exact' | 'network' | 'default'


@dataclass
class _Entry:
    p: float
    burst: float
    weight: float
    t: float             # 마지막 갱신 시각 (초)


def _dest_key(dest: str) -> str:
    """목적지를 프리픽스 키로 정규화한다. IPv4 -> /24, IPv6 -> /48.

    IP가 아닌 문자열(시뮬레이터의 불투명 라벨 등)은 그대로 쓴다.
    """
    try:
        addr = ipaddress.ip_address(dest)
    except ValueError:
        return dest
    if addr.version == 4:
        return str(ipaddress.ip_network(f"{addr}/24", strict=False))
    return str(ipaddress.ip_network(f"{addr}/48", strict=False))


class PathStatsCache:
    """(접속망, 목적지 프리픽스) -> 손실 통계. 표준 라이브러리만 사용."""

    NETWORK_AGG = "*"     # 망 집계 항목의 목적지 자리

    def __init__(self, half_life_s: float = 600.0, max_entries: int = 256,
                 w_cap: float = 1536.0, w_min: float = 25.0,
                 prior_out_cap: float = 100.0,
                 default_p: float = 0.01, default_burst: float = 1.0,
                 default_weight: float = 100.0):
        # w_cap(저장 상한)과 prior_out_cap(반출 상한)은 역할이 다르다.
        #  - 저장 가중치는 **신선도 예산**이다: 1536으로 저장된 항목은 반감기
        #    약 6번(1시간)을 버티고, 100짜리는 2번(20분)이면 w_min 밑으로
        #    떨어져 사라진다. 증거가 많던 항목일수록 오래 사는 게 맞다.
        #  - 반출 가중치는 **추정기가 받을 확신**이다. (w, z) 공동 튜닝 실측
        #    (2026-08-14, tune_cache.py): 반출 w가 100을 넘으면 "캐시가 낮게
        #    틀렸을 때"의 후회가 콜드 스타트를 초과한다(z=1.5에서 w=200이면
        #    39.4% vs 콜드 33.5%). 확신에 찬 캐시는 초반 헤지를 깎는 게
        #    정의라서 이건 파라미터로 안 풀린다 - 반출을 기본 사전과 같은
        #    100으로 제한하는 것이 "틀려도 콜드보다 나쁘지 않다"의 조건이었다.
        #    즉 캐시의 값어치는 확신이 아니라 **시작점(p, burst)**에 있다.
        self.half_life_s = half_life_s
        self.max_entries = max_entries
        self.w_cap = w_cap
        self.w_min = w_min
        self.prior_out_cap = prior_out_cap
        # 🩸 C5 (2026-08-18 감사): 반출 상한이 _get() 안에서만 걸려 있어
        # **캐시 미스(=콜드 스타트) 경로가 상한을 우회**했다. prior_out_cap=50
        # 으로 조여도 미스는 100 을 그대로 내줬다. 상한은 (w,z) 공동 튜닝이
        # 세운 유일한 안전 성질이므로 모든 반출 경로에 걸려야 한다.
        self.default = Prior(default_p, default_burst,
                             min(default_weight, prior_out_cap), "default")
        self._table: dict[tuple[str, str], _Entry] = {}

    # ---- 내부 ------------------------------------------------------

    def _decayed_weight(self, e: _Entry, now: float) -> float:
        age = max(now - e.t, 0.0)
        return e.weight * 0.5 ** (age / self.half_life_s)

    def _get(self, key: tuple[str, str], now: float) -> Prior | None:
        e = self._table.get(key)
        if e is None:
            return None
        w = self._decayed_weight(e, now)
        if w < self.w_min:
            del self._table[key]         # 발언권을 잃은 항목은 지운다
            return None
        return Prior(e.p, e.burst, min(w, self.prior_out_cap),
                     "exact" if key[1] != self.NETWORK_AGG else "network")

    def _merge(self, key: tuple[str, str], p: float, burst: float,
               w_new: float, now: float) -> None:
        old = self._table.get(key)
        if old is not None:
            w_old = self._decayed_weight(old, now)
            w = w_old + w_new
            p = (old.p * w_old + p * w_new) / w
            burst = (old.burst * w_old + burst * w_new) / w
        else:
            w = w_new
        self._table[key] = _Entry(p, burst, min(w, self.w_cap), now)

        if len(self._table) > self.max_entries:
            oldest = min(self._table, key=lambda k: self._table[k].t)
            del self._table[oldest]

    # ---- 공개 API --------------------------------------------------

    def lookup(self, network_id: str, dest: str,
               now: float | None = None) -> Prior:
        """사전값을 얻는다. 정확 항목 -> 망 집계 -> 기본값 순서."""
        now = time.monotonic() if now is None else now
        hit = self._get((network_id, _dest_key(dest)), now)
        if hit is not None:
            return hit
        hit = self._get((network_id, self.NETWORK_AGG), now)
        if hit is not None:
            return hit
        return self.default

    def store(self, network_id: str, dest: str, p: float, burst: float,
              evidence: float, now: float | None = None) -> None:
        """연결이 끝날 때 추정기 스냅샷을 반영한다.

        evidence는 LossEstimator.snapshot()의 세 번째 값 - **직접 관측한
        심볼 수만** 센 것이어야 한다. 물려받은 사전 가중치까지 더해 저장하면
        캐시를 거칠 때마다 증거가 눈덩이처럼 불어나, 몇 번 반복 후에는
        관측 몇천 심볼어치 확신을 주장하는 캐시가 된다.
        """
        if evidence <= 0.0:
            return
        now = time.monotonic() if now is None else now
        w = min(evidence, self.w_cap)
        self._merge((network_id, _dest_key(dest)), p, burst, w, now)
        self._merge((network_id, self.NETWORK_AGG), p, burst, w, now)

    def __len__(self) -> int:
        return len(self._table)
