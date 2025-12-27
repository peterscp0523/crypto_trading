#!/usr/bin/env python3
"""
자동 최적화 스크립트
Oracle DB에서 거래 성과를 분석하고, 필요시 파라미터 자동 조정
"""
import os
import sys
import json
from datetime import datetime, timedelta
import oracledb
import base64
import zipfile
import tempfile

# 성과 기준
MIN_WIN_RATE = 50.0  # 최소 승률 50%
MIN_PROFIT_RATE = 0.5  # 최소 평균 수익률 0.5%
CRITICAL_WIN_RATE = 40.0  # 긴급 개입 승률 40%
MIN_TRADES = 10  # 최소 거래 횟수


def connect_oracle_db():
    """Oracle DB 연결"""
    try:
        # Wallet 설정
        wallet_base64 = os.environ.get('ORACLE_WALLET_BASE64')
        wallet_dir = tempfile.mkdtemp()
        wallet_path = f'{wallet_dir}/wallet.zip'

        with open(wallet_path, 'wb') as f:
            f.write(base64.b64decode(wallet_base64))

        with zipfile.ZipFile(wallet_path, 'r') as zip_ref:
            zip_ref.extractall(wallet_dir)

        conn = oracledb.connect(
            user=os.environ.get('ORACLE_DB_USER', 'ADMIN'),
            password=os.environ.get('ORACLE_DB_PASSWORD'),
            dsn=os.environ.get('ORACLE_DB_DSN'),
            config_dir=wallet_dir,
            wallet_location=wallet_dir,
            wallet_password=os.environ.get('ORACLE_DB_PASSWORD')
        )

        print("✅ Oracle DB 연결 성공")
        return conn
    except Exception as e:
        print(f"❌ Oracle DB 연결 실패: {e}")
        return None


def analyze_recent_trades(conn, days=7):
    """최근 거래 분석"""
    cursor = conn.cursor()

    # 최근 N일 거래 조회
    cutoff_date = datetime.now() - timedelta(days=days)

    cursor.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
            AVG(profit_rate) as avg_profit_rate,
            AVG(hold_time_minutes) as avg_hold_time,
            MIN(profit_rate) as worst_trade,
            MAX(profit_rate) as best_trade
        FROM trades
        WHERE timestamp >= :cutoff_date
        AND trade_type = 'SELL'
    """, cutoff_date=cutoff_date)

    row = cursor.fetchone()
    cursor.close()

    if not row or row[0] == 0:
        return None

    total_trades, winning_trades, avg_profit_rate, avg_hold_time, worst_trade, best_trade = row

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate,
        'avg_profit_rate': avg_profit_rate or 0,
        'avg_hold_time': avg_hold_time or 0,
        'worst_trade': worst_trade or 0,
        'best_trade': best_trade or 0,
        'period_days': days
    }


def generate_optimization_plan(performance):
    """성과 기반 최적화 계획 생성"""

    optimizations = []
    is_critical = False

    # 1. 승률 체크
    if performance['win_rate'] < CRITICAL_WIN_RATE:
        is_critical = True
        optimizations.append({
            'type': 'RSI',
            'action': 'increase',
            'current': 42,
            'new': 48,
            'reason': f"승률 {performance['win_rate']:.1f}% (긴급: < {CRITICAL_WIN_RATE}%)"
        })
        optimizations.append({
            'type': 'VOLUME',
            'action': 'decrease',
            'current': 0.95,
            'new': 0.85,
            'reason': '거래량 조건 더욱 완화'
        })
    elif performance['win_rate'] < MIN_WIN_RATE:
        optimizations.append({
            'type': 'RSI',
            'action': 'increase',
            'current': 42,
            'new': 45,
            'reason': f"승률 {performance['win_rate']:.1f}% (목표: {MIN_WIN_RATE}%)"
        })

    # 2. 평균 수익률 체크
    if performance['avg_profit_rate'] < MIN_PROFIT_RATE:
        optimizations.append({
            'type': 'TAKE_PROFIT',
            'action': 'increase',
            'current': [1.5, 2.5, 4.0],
            'new': [1.8, 2.8, 4.5],
            'reason': f"평균 수익률 {performance['avg_profit_rate']:.2f}% 낮음"
        })

    # 3. 거래 횟수 체크
    if performance['total_trades'] < performance['period_days'] * 1:  # 하루 1회 미만
        optimizations.append({
            'type': 'BOLLINGER',
            'action': 'increase',
            'current': [1.10, 1.15, 1.20],
            'new': [1.15, 1.20, 1.25],
            'reason': f"거래 빈도 낮음 ({performance['total_trades']}회/{performance['period_days']}일)"
        })

    return {
        'optimizations': optimizations,
        'is_critical': is_critical,
        'performance': performance
    }


def apply_optimizations(plan):
    """최적화 적용 (파일 수정)"""

    if not plan['optimizations']:
        return False

    # telegram_bot.py 수정
    with open('telegram_bot.py', 'r', encoding='utf-8') as f:
        content = f.read()

    for opt in plan['optimizations']:
        if opt['type'] == 'RSI':
            # RSI 값 변경
            content = content.replace(
                f"self.rsi_buy = {opt['current']}",
                f"self.rsi_buy = {opt['new']}"
            )

        elif opt['type'] == 'VOLUME':
            # 거래량 임계값 변경
            content = content.replace(
                f"base_vol_threshold = {opt['current']}",
                f"base_vol_threshold = {opt['new']}"
            )

    # 파일 저장
    with open('telegram_bot.py', 'w', encoding='utf-8') as f:
        f.write(content)

    return True


def generate_report(plan):
    """최적화 리포트 생성"""

    perf = plan['performance']

    report = f"""# 🤖 자동 최적화 리포트

## 📊 거래 성과 분석 (최근 {perf['period_days']}일)

| 지표 | 값 | 목표 | 상태 |
|------|-----|------|------|
| **총 거래 횟수** | {perf['total_trades']}회 | {MIN_TRADES}회 이상 | {'✅' if perf['total_trades'] >= MIN_TRADES else '⚠️'} |
| **승률** | {perf['win_rate']:.1f}% | {MIN_WIN_RATE}% 이상 | {'✅' if perf['win_rate'] >= MIN_WIN_RATE else '❌'} |
| **평균 수익률** | {perf['avg_profit_rate']:.2f}% | {MIN_PROFIT_RATE}% 이상 | {'✅' if perf['avg_profit_rate'] >= MIN_PROFIT_RATE else '⚠️'} |
| **평균 보유 시간** | {perf['avg_hold_time']:.0f}분 | - | - |
| **최고 수익** | {perf['best_trade']:.2f}% | - | ✅ |
| **최악 손실** | {perf['worst_trade']:.2f}% | - | - |

"""

    if plan['optimizations']:
        report += "\n## 🔧 적용된 최적화\n\n"

        for i, opt in enumerate(plan['optimizations'], 1):
            report += f"### {i}. {opt['type']} 조정\n\n"
            report += f"- **변경**: {opt['current']} → {opt['new']}\n"
            report += f"- **이유**: {opt['reason']}\n"
            report += f"- **예상 효과**: "

            if opt['action'] == 'increase':
                report += "매수 기회 증가\n"
            elif opt['action'] == 'decrease':
                report += "승률 개선\n"

            report += "\n"

        if plan['is_critical']:
            report += "\n⚠️ **긴급 최적화**: 승률이 매우 낮아 자동 적용됩니다.\n"
        else:
            report += "\n💡 **리뷰 후 적용**: PR을 확인하고 수동으로 머지해주세요.\n"

    else:
        report += "\n## ✅ 최적화 불필요\n\n"
        report += "현재 성과가 목표치를 충족하고 있습니다.\n"

    return report


def main():
    """메인 함수"""

    print("🤖 자동 최적화 시작...")

    # 1. Oracle DB 연결
    conn = connect_oracle_db()
    if not conn:
        print("❌ DB 연결 실패 - 종료")
        sys.exit(1)

    # 2. 거래 성과 분석
    performance = analyze_recent_trades(conn, days=7)
    conn.close()

    if not performance:
        print("📊 거래 데이터 없음 - 최적화 스킵")
        sys.exit(0)

    print(f"📊 분석 완료: {performance['total_trades']}건, 승률 {performance['win_rate']:.1f}%")

    # 3. 최적화 필요 여부 확인
    if performance['total_trades'] < MIN_TRADES:
        print(f"⏳ 거래 횟수 부족 ({performance['total_trades']} < {MIN_TRADES}) - 스킵")
        sys.exit(0)

    # 4. 최적화 계획 생성
    plan = generate_optimization_plan(performance)

    if not plan['optimizations']:
        print("✅ 성과 양호 - 최적화 불필요")
        sys.exit(0)

    # 5. 최적화 적용
    print(f"🔧 최적화 적용 중... ({len(plan['optimizations'])}개 변경)")
    apply_optimizations(plan)

    # 6. 리포트 생성
    report = generate_report(plan)

    with open('optimization_report.md', 'w', encoding='utf-8') as f:
        f.write(report)

    # 7. 플래그 파일 생성
    with open('optimization_needed.flag', 'w') as f:
        f.write('1')

    if plan['is_critical']:
        with open('critical_optimization.flag', 'w') as f:
            f.write('1')

    print("✅ 최적화 완료!")
    print(report)


if __name__ == '__main__':
    main()
