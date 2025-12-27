#!/usr/bin/env python3
"""
데이터베이스 유지보수 스크립트
- 오래된 거래 데이터 아카이빙
- 공간 확보를 위한 자동 정리
"""
import os
import sys
from datetime import datetime, timedelta
from database_manager import DatabaseManager


def analyze_database_size(db):
    """데이터베이스 크기 분석"""
    try:
        if db.use_oracle:
            # Oracle DB 크기 조회
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT
                    SUM(bytes)/1024/1024 as size_mb
                FROM user_segments
                WHERE segment_name IN ('TRADES', 'OPTIMIZED_PARAMETERS')
            """)
            result = cursor.fetchone()
            size_mb = result[0] if result and result[0] else 0
            cursor.close()
        else:
            # SQLite DB 크기
            import sqlite3
            cursor = db.conn.cursor()
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_bytes = cursor.fetchone()[0]
            size_mb = size_bytes / 1024 / 1024
            cursor.close()

        return size_mb

    except Exception as e:
        print(f"⚠️ DB 크기 분석 실패: {e}")
        return 0


def get_trade_statistics(db):
    """거래 통계 조회"""
    try:
        cursor = db.conn.cursor()

        # 전체 거래 수
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]

        # 가장 오래된 거래
        cursor.execute("SELECT MIN(timestamp) FROM trades")
        oldest_trade = cursor.fetchone()[0]

        # 가장 최신 거래
        cursor.execute("SELECT MAX(timestamp) FROM trades")
        newest_trade = cursor.fetchone()[0]

        # 월별 거래 수
        cursor.execute("""
            SELECT
                EXTRACT(YEAR FROM timestamp) as year,
                EXTRACT(MONTH FROM timestamp) as month,
                COUNT(*) as count
            FROM trades
            GROUP BY EXTRACT(YEAR FROM timestamp), EXTRACT(MONTH FROM timestamp)
            ORDER BY year DESC, month DESC
        """)
        monthly_stats = cursor.fetchall()

        cursor.close()

        return {
            'total_trades': total_trades,
            'oldest_trade': oldest_trade,
            'newest_trade': newest_trade,
            'monthly_stats': monthly_stats
        }

    except Exception as e:
        print(f"⚠️ 통계 조회 실패: {e}")
        return None


def archive_old_trades(db, months_to_keep=6, dry_run=True):
    """오래된 거래 아카이빙

    Args:
        db: DatabaseManager 인스턴스
        months_to_keep: 보관할 개월 수 (기본 6개월)
        dry_run: True면 실제 삭제하지 않고 시뮬레이션
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=months_to_keep * 30)

        cursor = db.conn.cursor()

        # 삭제 대상 조회
        cursor.execute("""
            SELECT COUNT(*) FROM trades
            WHERE timestamp < :cutoff_date
        """, cutoff_date=cutoff_date)

        count_to_delete = cursor.fetchone()[0]

        if count_to_delete == 0:
            print(f"✅ 삭제할 오래된 거래 없음 ({cutoff_date.strftime('%Y-%m-%d')} 이전)")
            cursor.close()
            return 0

        print(f"\n📦 아카이빙 대상: {count_to_delete}건 ({cutoff_date.strftime('%Y-%m-%d')} 이전)")

        if dry_run:
            print("🔍 DRY RUN 모드 - 실제 삭제하지 않음")
            cursor.close()
            return count_to_delete

        # 실제 삭제
        cursor.execute("""
            DELETE FROM trades
            WHERE timestamp < :cutoff_date
        """, cutoff_date=cutoff_date)

        db.conn.commit()
        cursor.close()

        print(f"✅ {count_to_delete}건 삭제 완료")
        return count_to_delete

    except Exception as e:
        print(f"❌ 아카이빙 실패: {e}")
        if db.conn:
            db.conn.rollback()
        return 0


def vacuum_database(db):
    """데이터베이스 최적화 (공간 회수)"""
    try:
        if not db.use_oracle:
            # SQLite만 VACUUM 지원
            cursor = db.conn.cursor()
            cursor.execute("VACUUM")
            cursor.close()
            print("✅ 데이터베이스 최적화 완료 (VACUUM)")
        else:
            # Oracle은 자동 공간 관리
            print("ℹ️  Oracle DB는 자동 공간 관리됨")

    except Exception as e:
        print(f"⚠️ 최적화 실패: {e}")


def main():
    """메인 함수"""

    print("=" * 60)
    print("🔧 데이터베이스 유지보수")
    print("=" * 60)

    # 환경변수에서 설정 읽기
    use_oracle = os.environ.get('USE_ORACLE_DB', 'false').lower() == 'true'
    dry_run = len(sys.argv) < 2 or sys.argv[1] != '--apply'
    months_to_keep = int(os.environ.get('DB_ARCHIVE_MONTHS', '6'))

    if dry_run:
        print("\n🔍 DRY RUN 모드 (실제 삭제 안함)")
        print("실제 삭제하려면: python db_maintenance.py --apply\n")
    else:
        print("\n⚠️ 실제 삭제 모드 활성화\n")

    # DB 연결
    try:
        db = DatabaseManager(use_oracle=use_oracle)
        print(f"✅ DB 연결: {'Oracle' if use_oracle else 'SQLite'}\n")
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        sys.exit(1)

    # 1. DB 크기 분석
    print("📊 데이터베이스 분석")
    print("-" * 60)

    size_mb = analyze_database_size(db)
    print(f"💾 DB 크기: {size_mb:.2f} MB")

    if use_oracle:
        usage_pct = (size_mb / (20 * 1024)) * 100  # 20GB = 20,480 MB
        print(f"📈 사용률: {usage_pct:.2f}% / 20GB (Oracle Free Tier)")

        if usage_pct > 80:
            print("⚠️ 경고: 사용률 80% 초과 - 아카이빙 권장!")
        elif usage_pct > 50:
            print("ℹ️  주의: 사용률 50% 초과")

    # 2. 거래 통계
    stats = get_trade_statistics(db)

    if stats:
        print(f"\n📈 거래 통계")
        print("-" * 60)
        print(f"전체 거래: {stats['total_trades']:,}건")

        if stats['oldest_trade']:
            print(f"가장 오래된 거래: {stats['oldest_trade']}")
        if stats['newest_trade']:
            print(f"가장 최신 거래: {stats['newest_trade']}")

        if stats['monthly_stats']:
            print(f"\n월별 거래 현황 (최근 5개월):")
            for i, (year, month, count) in enumerate(stats['monthly_stats'][:5]):
                print(f"  {int(year)}-{int(month):02d}: {count:,}건")

    # 3. 아카이빙
    print(f"\n🗄️ 데이터 아카이빙 ({months_to_keep}개월 이전 데이터)")
    print("-" * 60)

    deleted_count = archive_old_trades(db, months_to_keep=months_to_keep, dry_run=dry_run)

    # 4. 최적화
    if not dry_run and deleted_count > 0:
        print(f"\n🔧 데이터베이스 최적화")
        print("-" * 60)
        vacuum_database(db)

    # 5. 최종 크기
    if not dry_run and deleted_count > 0:
        print(f"\n📊 최종 상태")
        print("-" * 60)
        new_size_mb = analyze_database_size(db)
        print(f"💾 DB 크기: {size_mb:.2f} MB → {new_size_mb:.2f} MB")
        saved_mb = size_mb - new_size_mb
        if saved_mb > 0:
            print(f"✅ 절약된 공간: {saved_mb:.2f} MB")

    db.close()

    print("\n" + "=" * 60)
    print("✅ 유지보수 완료")
    print("=" * 60)


if __name__ == '__main__':
    main()
