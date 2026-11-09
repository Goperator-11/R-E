import io
import sys

P = "C:/dev/pq_afec/experiments/quicbed/qfec.go"


def main():
    s = io.open(P, encoding="utf-8").read()
    n = 0

    old_row = """func cauchyRow(k, j int) []byte {
	row := make([]byte, k)
	for i := 0; i < k; i++ {
		row[i] = gfInv(byte(k+j) ^ byte(i))
	}
	return row
}"""
    new_row = """func cauchyRow(m, p, k int) []byte {
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
