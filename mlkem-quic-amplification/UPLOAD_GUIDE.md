폴더가 독립 리포이던 때의 안내다. 지금은 R-E 폴더이므로 쓰지 않는다.

# 깃허브 업로드 방법

> **Private으로 만드세요.** 미발표 연구입니다.

## 1. 리포지토리 생성

github.com → New repository

- Repository name: `mlkem-quic-amplification` (자유)
- **Visibility: Private** ← 중요
- Add README / .gitignore / license: **전부 체크 해제** (이미 있음)

## 2. 업로드 — 방법 A: 웹 드래그앤드롭 (쉬움)

1. 만든 리포 페이지에서 **uploading an existing file** 클릭
2. 압축 푼 폴더의 **내용물 전체**를 드래그
   (폴더째가 아니라 안의 파일·폴더들을 선택)
3. 아래 Commit changes 클릭

`.gitignore`처럼 점으로 시작하는 파일은 드래그로 안 올라갈 수 있습니다. 안 올라가면 **Add file → Create new file**로 이름 `.gitignore` 입력 후 내용 붙여넣기.

## 3. 업로드 — 방법 B: 명령줄

```bash
cd 압축푼폴더
git init
git add .
git commit -m "R&E 연구 자료 전체 — 코드, 문서, 데이터"
git branch -M main
git remote add origin https://github.com/<아이디>/<리포이름>.git
git push -u origin main
```

비밀번호를 물으면 계정 비밀번호가 아니라 **Personal Access Token**이 필요합니다.
Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token → `repo` 체크

## 4. 팀원 초대

리포 → Settings → Collaborators → Add people → 상대 깃허브 아이디

Private이어도 초대한 사람은 다 볼 수 있습니다.

---

## 올린 뒤 확인할 것

- [ ] Private으로 되어 있는가 (리포 이름 옆에 `Private` 배지)
- [ ] `docs/종합기술문서.pdf`가 열리는가 (3MB, 깃허브 100MB 제한 내)
- [ ] README가 첫 화면에 보이는가

---

## 나중에 공개 전환할 때

학회 발표 후 Public으로 바꾸려면 그 전에 지울 것:

- 서버 이름 `kebap-server`
- 경로에 든 실명 (`1311 신레오`) — README, 종합기술문서, run_v3.sh 주석
- 팀원 실명 (필요시 팀원 A/B/C로)

`git log`에도 남으니 커밋 메시지에 민감한 정보를 넣지 마세요.
