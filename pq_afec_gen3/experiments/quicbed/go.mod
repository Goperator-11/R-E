// 🩸 2026-09-03 - 이 파일이 여태 **저장소 밖에** 있었다.
//
// build.sh 는 소스를 $HOME/quicbed 로 복사해 거기서 빌드하는데, 모듈 정의는
// 그 작업 디렉터리 안에서 한 번 `go mod init` 한 뒤로 쭉 거기에만 있었다.
// 그래서 clone 한 사람은 Go 쪽을 **재현할 수 없었다** - build.sh 의
// `go mod tidy >/dev/null 2>&1 || true` 가 그 실패를 조용히 삼켰기 때문에
// 증상은 "빌드가 안 된다" 가 아니라 "go.mod 가 없다" 는 낯선 에러였다.
// (.gitignore 문제가 아니다. 여기에 파일이 애초에 존재한 적이 없다.)
//
// **버전을 고정한 채로** 저장소에 둔다. `go mod init` 으로 대신하면 quic-go
// 버전이 그때그때 최신으로 잡혀 재현성이 오히려 깨진다 - 우리가 실측한
// 수치는 전부 quic-go v0.61.0 의 것이다(InitialPacketSize 1452 절삭,
// isAmplificationLimited 의 불리언 게이트 등 README 「한계」 절 참고).

module pqafec/quicbed

go 1.26.6

require github.com/quic-go/quic-go v0.61.0

require (
	golang.org/x/crypto v0.54.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
)
