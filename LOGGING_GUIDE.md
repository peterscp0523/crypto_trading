# 봇 로그 모니터링 가이드

## 🎯 목적별 로그 확인 방법

### 1️⃣ 실시간 로그 모니터링 (로컬에서)

**가장 간단한 방법:**

```bash
./watch_logs.sh
```

**또는 직접 SSH:**

```bash
ssh -i ~/.ssh/github_actions_oracle opc@140.245.69.95 \
  "docker logs -f --tail 100 crypto-trading-bot"
```

**옵션:**
- `-f` 또는 `--follow`: 실시간 추적
- `--tail N`: 최근 N줄만 표시
- `--since 5m`: 최근 5분간 로그만
- `--timestamps`: 타임스탬프 포함

**종료:** `Ctrl+C`

---

### 2️⃣ GitHub Actions로 원격 로그 확인

1. GitHub 저장소 방문
2. **Actions** 탭 클릭
3. **"Watch Bot Logs"** 워크플로우 선택
4. **"Run workflow"** 클릭
5. 옵션 설정:
   - `lines`: 로그 줄 수 (기본 100)
   - `follow`: 실시간 추적 (true/false)

---

### 3️⃣ 로컬에서 Docker Compose로 테스트

**테스트 환경 실행:**

```bash
docker-compose up -d
```

**실시간 로그 보기:**

```bash
docker-compose logs -f trading-bot
```

**특정 시간대 로그:**

```bash
docker-compose logs --since 1h trading-bot
```

**종료:**

```bash
docker-compose down
```

---

## 📊 유용한 로그 필터링

### 매수/매도만 보기

```bash
docker logs crypto-trading-bot 2>&1 | grep -E "매수|매도"
```

### 에러만 보기

```bash
docker logs crypto-trading-bot 2>&1 | grep -E "ERROR|❌|실패"
```

### 최근 1시간 로그

```bash
docker logs --since 1h crypto-trading-bot
```

### 특정 시간 범위

```bash
docker logs --since "2025-12-28T09:00:00" \
            --until "2025-12-28T10:00:00" \
            crypto-trading-bot
```

---

## 🔧 고급 모니터링

### 1. 로그 파일로 저장

```bash
ssh opc@140.245.69.95 \
  "docker logs crypto-trading-bot" > bot_logs_$(date +%Y%m%d_%H%M%S).txt
```

### 2. 실시간 로그를 파일로 저장하면서 보기

```bash
ssh opc@140.245.69.95 \
  "docker logs -f crypto-trading-bot" | tee bot_logs.txt
```

### 3. JSON 형식 로그 분석

Docker는 로그를 JSON 파일로 저장합니다:

```bash
ssh opc@140.245.69.95
sudo cat /var/lib/docker/containers/$(docker ps -aqf "name=crypto-trading-bot")/$(docker ps -aqf "name=crypto-trading-bot")-json.log
```

---

## 📈 로그 레벨별 의미

| 기호 | 의미 | 설명 |
|------|------|------|
| ✅ | 성공 | 정상 작동 |
| ⚠️ | 경고 | 주의 필요하지만 계속 작동 |
| ❌ | 에러 | 오류 발생, 확인 필요 |
| 🔍 | 정보 | 일반 정보 |
| 💰 | 매수 | 매수 발생 |
| 💸 | 매도 | 매도 발생 |
| 📊 | 분석 | 시장 분석 결과 |
| 🐻 | 약세장 | 약세장 감지 |
| 🐂 | 강세장 | 강세장 감지 |

---

## 🚨 문제 해결

### 로그가 안 보일 때

**컨테이너 상태 확인:**

```bash
ssh opc@140.245.69.95 "docker ps -a | grep crypto"
```

**컨테이너가 중지됨:**

```bash
ssh opc@140.245.69.95 "docker start crypto-trading-bot"
```

**컨테이너가 없음:**

재배포 필요:

```bash
git push origin main  # GitHub Actions가 자동 배포
```

### SSH 접속 안 될 때

**SSH 키 확인:**

```bash
ls -la ~/.ssh/github_actions_oracle
```

**키 권한 수정:**

```bash
chmod 600 ~/.ssh/github_actions_oracle
```

---

## 🎬 빠른 시작

**1. 지금 당장 로그 보기:**

```bash
./watch_logs.sh
```

**2. 최근 매수/매도 확인:**

```bash
ssh opc@140.245.69.95 "docker logs --tail 500 crypto-trading-bot" | grep -E "매수|매도"
```

**3. 에러 있는지 확인:**

```bash
ssh opc@140.245.69.95 "docker logs --tail 200 crypto-trading-bot" | grep -E "ERROR|❌|실패"
```

---

## 💡 팁

1. **터미널 2개 사용**
   - 터미널 1: 실시간 로그 모니터링 (`./watch_logs.sh`)
   - 터미널 2: 명령어 실행

2. **로그 색상 강조**
   - `grep`에 `--color=always` 옵션 추가

3. **로그 자동 새로고침**
   - `watch` 명령어 사용:
     ```bash
     watch -n 5 'ssh opc@140.245.69.95 "docker logs --tail 20 crypto-trading-bot"'
     ```

4. **알림 설정**
   - 매수/매도 발생 시 텔레그램으로 알림 (이미 구현됨)
