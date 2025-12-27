# 🗄️ 데이터베이스 유지보수 가이드

Oracle Cloud Free Tier는 **20GB 스토리지**를 제공합니다. 거래 데이터가 쌓이면서 공간이 부족해질 수 있으므로, 자동 아카이빙 시스템을 구현했습니다.

---

## 📊 자동 유지보수 시스템

### 실행 주기
- **자동 실행**: 매월 1일 새벽 2시 (KST 11시)
- **수동 실행**: GitHub Actions에서 언제든지 실행 가능

### 기본 정책
- **보관 기간**: 최근 6개월 거래만 유지
- **삭제 대상**: 6개월 이전 거래 데이터
- **모드**: 기본적으로 DRY RUN (시뮬레이션만)

---

## 🔍 현재 상태 확인

### 로컬에서 확인
```bash
# DRY RUN 모드 (삭제하지 않고 확인만)
python scripts/db_maintenance.py

# 출력 예시:
# 📊 데이터베이스 분석
# 💾 DB 크기: 45.23 MB
# 📈 사용률: 0.22% / 20GB (Oracle Free Tier)
#
# 📈 거래 통계
# 전체 거래: 1,234건
# 가장 오래된 거래: 2024-06-15
# 가장 최신 거래: 2024-12-27
#
# 월별 거래 현황:
#   2024-12: 150건
#   2024-11: 200건
#   ...
```

### GitHub Actions에서 확인
GitHub → Actions → "Database Maintenance" → Run workflow

---

## 🗑️ 오래된 데이터 삭제

### 수동 삭제 (로컬)
```bash
# 6개월 이전 데이터 삭제
python scripts/db_maintenance.py --apply

# 3개월 이전 데이터 삭제 (보관 기간 단축)
DB_ARCHIVE_MONTHS=3 python scripts/db_maintenance.py --apply
```

### 수동 삭제 (GitHub Actions)
1. GitHub → Actions → "Database Maintenance"
2. Run workflow 클릭
3. 옵션 설정:
   - `dry_run`: `false` (실제 삭제)
   - `months_to_keep`: `6` (보관 개월 수)
4. Run workflow 실행

---

## 📋 예상 데이터 증가율

### 거래 빈도별 예상
| 거래 빈도 | 월 평균 거래 | 연간 데이터 | 6개월 데이터 |
|-----------|--------------|-------------|--------------|
| **저빈도** (하루 1-2회) | ~50건 | ~600건 | ~300건 |
| **중빈도** (하루 5-10회) | ~200건 | ~2,400건 | ~1,200건 |
| **고빈도** (하루 20-50회) | ~1,000건 | ~12,000건 | ~6,000건 |

### 예상 용량
- **1건당**: ~0.5 KB (거래 기록 + 메타데이터)
- **1,000건**: ~0.5 MB
- **10,000건**: ~5 MB
- **100,000건**: ~50 MB

**결론**: 20GB 한도 내에서 **수년치** 데이터 저장 가능

---

## ⚙️ 보관 정책 커스터마이징

### 환경변수로 설정
`.github/workflows/db-maintenance.yml` 수정:

```yaml
env:
  DB_ARCHIVE_MONTHS: 12  # 6개월 → 12개월로 변경
```

### 로컬 실행 시
```bash
# 12개월 보관
DB_ARCHIVE_MONTHS=12 python scripts/db_maintenance.py --apply

# 3개월만 보관 (공간 부족 시)
DB_ARCHIVE_MONTHS=3 python scripts/db_maintenance.py --apply
```

---

## 🚨 공간 부족 시 대응

### 경고 임계값
- **50% 사용**: 주의 (ℹ️)
- **80% 사용**: 경고 (⚠️) - 아카이빙 권장

### 긴급 대응 (80% 초과)
```bash
# 1. 즉시 3개월 이전 데이터 삭제
DB_ARCHIVE_MONTHS=3 python scripts/db_maintenance.py --apply

# 2. 1개월 이전 데이터 삭제 (최후 수단)
DB_ARCHIVE_MONTHS=1 python scripts/db_maintenance.py --apply
```

---

## 📤 데이터 백업 (선택 사항)

삭제 전 중요 데이터를 백업하려면:

```python
# backup_trades.py (별도 스크립트 작성 필요)
import csv
from database_manager import DatabaseManager
from datetime import datetime, timedelta

db = DatabaseManager(use_oracle=True)
cursor = db.conn.cursor()

# 6개월 이전 데이터 조회
cutoff_date = datetime.now() - timedelta(days=180)
cursor.execute("SELECT * FROM trades WHERE timestamp < :cutoff", cutoff=cutoff_date)

# CSV로 저장
with open('archived_trades.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow([desc[0] for desc in cursor.description])
    writer.writerows(cursor)

print("✅ 백업 완료: archived_trades.csv")
```

---

## 📊 모니터링

### 텔레그램 알림
매월 유지보수 실행 시 자동 알림:
```
✅ DB 유지보수 완료
━━━━━━━━━━━━━━━━━

📊 Oracle DB 정리 완료
🔧 오래된 데이터 아카이빙 성공
```

### GitHub Actions 로그
- Actions → Database Maintenance → 최신 실행 로그
- 삭제된 거래 수, DB 크기 변화 확인 가능

---

## 🔒 안전장치

1. **기본 DRY RUN**: 실수로 삭제 방지
2. **수동 승인**: GitHub Actions에서 명시적으로 `dry_run=false` 설정 필요
3. **최근 6개월 보장**: 기본값으로 최근 데이터 보호
4. **트랜잭션**: 삭제 실패 시 자동 롤백

---

## 📚 참고

- Oracle Free Tier: 20GB 스토리지, 무제한 기간
- 거래 기록 1건 = 약 0.5KB
- 예상 수명: 현재 거래 빈도 기준 **10년 이상**
