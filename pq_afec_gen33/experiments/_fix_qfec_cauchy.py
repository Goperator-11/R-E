# -*- coding: utf-8 -*-
"""qfec.go 수정 두 가지. 측정 단계가 끝난 뒤 적용한다.

1) Cauchy 생성행렬 명세를 afec/rs.py 와 통일한다.
   두 구현이 각자는 정상 동작하지만 **행렬이 달라서 서로 호환되지 않았다**.
   p5 교차검증이 k>=3, m=2 에서 이걸 잡았다. 명세는 먼저 있었던 쪽
   (afec/rs.py, 1차에서 E16 완전탐색 감사를 통과한 구현)으로 고정한다.

       Python:  cauchy[p][o] = gf_inv(p ^ (m + o))     p=패리티, o=원본, m=패리티수
       Go(전):  row[o]       = gfInv((k + p) ^ o)      <- 다른 행렬
       Go(후):  row[o]       = gfInv(p ^ (m + o))      <- 일치

   k=2, m=2 에서만 우연히 같은 값이 나와(XOR 대칭) 그 조합은 통과했었다.

2) m >= 2 일 때 '신용 패리티'를 **첫 원본 다음**으로 옮긴다.
   전에는 비행의 맨 앞에 보냈는데, 그러면 서버에 아직 그 DCID 의 연결이
   없어서 quic-go 가 연결에 귀속시키기 전에 버릴 수 있다. 그러면 바이트가
   증폭 예산에 안 잡혀 신용이 통째로 사라진다. 첫 원본이 연결을 만든 뒤에
   보내면 확실히 계상된다.

       전:  [패리티0, 원본0..k-1, 패리티1..]
       후:  [원본0, 패리티0, 원본1..k-1, 패리티1..]

   두 경우 모두 마지막에 오는 것은 복호 가능한 원본이 아니라 복구용
   패리티인데, 복구용 패리티는 신용을 노리지 않으므로 문제가 없다.
   신용용 패리티는 마지막 원본보다 앞이라 quic-go 의
   `if !wasProcessed { continue }` 를 우회한다.
"""
import io
import os
import sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quicbed", "qfec.go")


def historical_patch():
    s = io.open(P, encoding="utf-8").read()
    n = 0

    old_row = """// cauchyRow 는 패리티 j 행의 계수 k 개를 돌려준다. x_j = k+j, y_i = i.
func cauchyRow(k, j int) []byte {
	row := make([]byte, k)
	for i := 0; i < k; i++ {
		row[i] = gfInv(byte(k+j) ^ byte(i))
	}
	return row
}"""
    new_row = """// cauchyRow 는 패리티 p 행의 계수 k 개를 돌려준다.
//
// 🩸 명세는 afec/rs.py 와 같아야 한다. 처음에는 x_p = k+p, y_o = o 로 잡았는데
// Python 은 x_p = p, y_o = m+o 를 쓴다. 둘 다 유효한 Cauchy 행렬이라 각자는
// 정상 복구되지만 **서로 호환되지 않는다.** k=2,m=2 에서만 XOR 대칭 때문에
// 우연히 같은 값이 나와 그 조합만 통과했고, p5 교차검증이 k>=3 에서 잡았다.
// "아무거나 골라도 되는" 자유도가 있는 곳이 정확히 어긋난다.
func cauchyRow(m, p, k int) []byte {
	row := make([]byte, k)
	for o := 0; o < k; o++ {
		row[o] = gfInv(byte(p) ^ byte(m+o))
	}
	return row
}"""
    if old_row in s:
        s = s.replace(old_row, new_row, 1)
        n += 1

    s2 = s.replace("row := cauchyRow(k, j)", "row := cauchyRow(m, j, k)")
    if s2 != s:
        s, n = s2, n + 1
    s2 = s.replace("row := cauchyRow(k, parityIdx)",
                   "row := cauchyRow(m, parityIdx, k)")
    if s2 != s:
        s, n = s2, n + 1

    # 2) 신용 패리티 위치 변경은 **적용하지 않는다.**
    #    p2 실측에서 on1(패리티 맨 뒤)도 임계를 5,917 -> 10,901 B 로 올렸다.
    #    quic-go 는 깨어날 때 수신 큐를 배치로 훑으므로, 같은 버스트로 보낸
    #    패리티가 마지막 원본과 같은 배치에 들어가 송신 결정 전에 계상된다.
    #    앞서 E21 의 dup1 이 실패한 것은 심의 3 ms 지연 때문에 다른 배치로
    #    밀렸기 때문이었다. 추측으로 순서를 바꾸면 잘 도는 것을 건드리는 것이
    #    되고, 측정도 통째로 다시 해야 한다.

    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("적용된 수정 %d 곳" % n)
    return 0 if n == 3 else 1


def main():
    print("This historical source patch is disabled in gen33.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
