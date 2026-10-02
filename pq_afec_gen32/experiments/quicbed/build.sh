#!/bin/bash
echo "Historical builder disabled in gen32; use build_gen32.sh" >&2
exit 2
# 문서 6절 함정: CGO_ENABLED=0 은 필수다(conda 가 CC 를 미설치 컴파일러로
# 지정해 두면 빌드가 실패한다). 우리 환경에도 그대로 적용해 둔다.
set -e
# 🩸 2026-09-03 - GOROOT 을 무조건 `$HOME/goroot` 로 덮어쓰고 있었다. 이 기계는
#    setup.sh 가 거기에 Go 를 풀어 놨으니 맞지만, clone 한 사람에게는 **시스템
#    Go 가 깔려 있어도** `go: cannot find GOROOT directory` 로 죽는 줄이다.
#    (실제로 fresh HOME 에서는 go.mod 에러가 아니라 `go: command not found`
#    exit 127 이 먼저 난다 - 그래서 진짜 원인이 안 보였다.) 있을 때만 쓴다.
if [ -d "$HOME/goroot" ]; then
	export GOROOT="$HOME/goroot"
	export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0
command -v go >/dev/null || {
	echo "go 를 못 찾겠다. Go 1.26.6 이상을 깔고 PATH 에 넣어라" >&2
	echo "(이 기계는 setup.sh 가 \$HOME/goroot 에 풀어 둔 것을 쓴다)" >&2
	exit 2
}

# 🩸 2026-09-03 - SRC 이 `/mnt/c/dev/pq_afec/...` 로 박혀 있었다. 이 기계에서는
#    맞지만 clone 한 사람에게는 틀린 경로다. 스크립트 제 위치에서 뽑는다.
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed"
mkdir -p "$WORK/cmd/server" "$WORK/cmd/client" "$WORK/cmd/dataapp" \
         "$WORK/cmd/qamp" "$WORK/cmd/mlkemcheck" "$WORK/bin"

# 🩸 2026-09-03 - 모듈 정의가 **저장소 밖에** 있었다. 여기 $WORK 안에서 한 번
#    `go mod init` 한 뒤로 쭉 이 작업 디렉터리에만 있었고, 그래서 clone 한
#    사람은 Go 쪽을 재현할 수 없었다. 아래 `go mod tidy … || true` 가 그
#    실패를 조용히 삼켰다. 이제 저장소의 것을 복사하고, **없으면 큰 소리로
#    죽는다.** 조용히 넘어가면 다음 사람이 또 같은 자리에서 헤맨다.
for m in go.mod go.sum; do
	if [ ! -f "$SRC/$m" ]; then
		echo "$SRC/$m 이 없다. 저장소에서 빠졌다 - 이 파일 없이는" >&2
		echo "quic-go 버전이 고정되지 않아 실측을 재현할 수 없다." >&2
		exit 2
	fi
	cp "$SRC/$m" "$WORK/$m"
done

# strip CRLF - the sources live on a Windows filesystem
sed 's/\r$//' "$SRC/server.go" > "$WORK/cmd/server/main.go"
sed 's/\r$//' "$SRC/client.go" > "$WORK/cmd/client/main.go"
sed 's/\r$//' "$SRC/dataapp.go" > "$WORK/cmd/dataapp/main.go"
sed 's/\r$//' "$SRC/qamp.go" > "$WORK/cmd/qamp/main.go"
sed 's/\r$//' "$SRC/policy.go" > "$WORK/cmd/qamp/policy.go"
sed 's/\r$//' "$SRC/pfail_table.go" > "$WORK/cmd/qamp/pfail_table.go"
sed 's/\r$//' "$SRC/mlkemcheck.go" > "$WORK/cmd/mlkemcheck/main.go"

cd "$WORK"
# 🩸 2026-09-03 - 여기 있던 `go mod tidy >/dev/null 2>&1 || true` 를 뺐다.
#    go.mod 가 없을 때 그 실패를 삼키는 것이 위 사고의 원인이었고, 있을 때는
#    tidy 가 $WORK 의 go.mod 를 저장소본과 다르게 고쳐 놓을 수 있다(그러면
#    빌드된 것과 저장소가 가리키는 것이 갈린다). readonly 로 못 박는다.
export GOFLAGS=-mod=readonly
go build -o "$WORK/bin/qserver" ./cmd/server
go build -o "$WORK/bin/qclient" ./cmd/client
go build -o "$WORK/bin/qdata" ./cmd/dataapp
CGO_ENABLED=0 go build -o "$WORK/bin/qamp" ./cmd/qamp
CGO_ENABLED=0 go build -o "$WORK/bin/mlkemcheck" ./cmd/mlkemcheck

# 🆕 2026-09-03 - **빌드 지문.** 이 바이너리가 어느 소스에서 나왔는지 옆에
#    적어 둔다. 관문(gate_go_parity.py)이 저장소 소스로 같은 지문을 떠서
#    대조하고, 어긋나면 실패한다.
#
#    왜 필요한가: 2026-08-29 에 표(P_VALS)와 반복 라운드 항이 바뀌었는데
#    관문을 **직접** 부르면 빌드가 안 일어난다. 옛 바이너리로 178,200 점을
#    돌면 불일치 5,016 건 · J 최대 46 ms 가 나오는데, 이걸 알고리즘 결함으로
#    읽으면 멀쩡한 모형을 뜯게 된다(실제로 외부 리뷰가 그렇게 읽었다).
#    관문의 형식 검사(열 13 개)는 열 수가 안 바뀐 표류를 원리적으로 못 본다.
#
#    지문은 **원본 바이트 그대로** 뜬다(CRLF 를 벗기지 않는다). 벗긴 뒤에 뜨면
#    bash 의 `sed 's/\r$//'` 과 Python 쪽 정규화가 미묘하게 달라질 수 있는데,
#    원본이 같으면 벗긴 것도 같으므로 원본을 재는 쪽이 엄격하면서 단순하다.
#    목록은 quicbed 의 *.go 전부 + build.sh + go.mod + go.sum 이다.
#    의존성 버전이 바뀌어도 바이너리를 다시 빌드해야 한다. loop2.py의 BED와 같은
#    범위이고, 같은 이유다(파일이 늘거나 줄어도 사람이 목록을 안 고쳐도 된다).
{
	cd "$SRC"
	for f in $(ls *.go build.sh go.mod go.sum 2>/dev/null | LC_ALL=C sort); do
		printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
	done
} | sha256sum | cut -d' ' -f1 > "$WORK/bin/qamp.srcsha"
cd "$WORK"

# 문서 5절: 경로 공백 회피를 위해 /tmp 로 복사해 실행한다.
cp "$WORK/bin/qamp" /tmp/qamp
cp "$WORK/bin/mlkemcheck" /tmp/mlkemcheck
cp "$WORK/bin/qamp.srcsha" /tmp/qamp.srcsha
echo "built:"
ls -la "$WORK/bin"
echo "소스 지문: $(cat "$WORK/bin/qamp.srcsha")"
