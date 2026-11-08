import io
import sys

P = "C:/dev/pq_afec/experiments/quicbed/qfec.go"


def main():
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

    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("적용된 수정 %d 곳" % n)
    return 0 if n == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
