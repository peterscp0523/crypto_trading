"""
Oracle Cloud Database Manager
Always Free Tier Autonomous Database 연동 및 데이터 관리
"""
import os
import json
from datetime import datetime, timedelta
import sqlite3  # 로컬 개발용
# Oracle DB는 cx_Oracle 사용 (배포 시)


class DatabaseManager:
    """데이터베이스 관리 (Oracle Cloud / SQLite)"""

    def __init__(self, use_oracle=False):
        """
        Args:
            use_oracle: True면 Oracle DB, False면 로컬 SQLite
        """
        self.use_oracle = use_oracle

        if use_oracle:
            # Oracle Cloud Autonomous Database 연결
            try:
                import cx_Oracle
                self.conn = cx_Oracle.connect(
                    user=os.environ.get('ORACLE_DB_USER', 'ADMIN'),
                    password=os.environ.get('ORACLE_DB_PASSWORD'),
                    dsn=os.environ.get('ORACLE_DB_DSN')
                )
                print("✅ Oracle Database 연결 성공")
            except Exception as e:
                print(f"⚠️ Oracle DB 연결 실패, SQLite 사용: {e}")
                self.use_oracle = False
                self.conn = sqlite3.connect('trading_data.db')
        else:
            # 로컬 SQLite
            self.conn = sqlite3.connect('trading_data.db')
            print("✅ SQLite Database 연결")

        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """테이블 생성"""

        # 1. 캔들 데이터 테이블
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market VARCHAR(20) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                timestamp DATETIME NOT NULL,
                open_price DECIMAL(20, 8),
                high_price DECIMAL(20, 8),
                low_price DECIMAL(20, 8),
                close_price DECIMAL(20, 8),
                volume DECIMAL(30, 8),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(market, timeframe, timestamp)
            )
        ''')

        # 2. 거래 기록 테이블
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market VARCHAR(20) NOT NULL,
                trade_type VARCHAR(10) NOT NULL,
                price DECIMAL(20, 8),
                amount DECIMAL(30, 8),
                krw_amount DECIMAL(20, 2),
                profit DECIMAL(20, 2),
                profit_rate DECIMAL(10, 4),
                reason VARCHAR(100),
                hold_time_minutes INTEGER,
                peak_profit DECIMAL(10, 4),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. 파라미터 최적화 기록
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS parameter_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market VARCHAR(20),
                optimization_date DATETIME,
                quick_profit DECIMAL(6, 4),
                take_profit_1 DECIMAL(6, 4),
                take_profit_2 DECIMAL(6, 4),
                stop_loss DECIMAL(6, 4),
                trailing_stop_tight DECIMAL(6, 4),
                trailing_stop_medium DECIMAL(6, 4),
                trailing_stop_wide DECIMAL(6, 4),
                backtest_return DECIMAL(10, 2),
                backtest_winrate DECIMAL(6, 2),
                backtest_sharpe DECIMAL(10, 4),
                score DECIMAL(10, 2),
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. 일일 성과 요약
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                total_trades INTEGER,
                winning_trades INTEGER,
                win_rate DECIMAL(6, 2),
                total_profit DECIMAL(20, 2),
                best_trade DECIMAL(10, 2),
                worst_trade DECIMAL(10, 2),
                avg_hold_time_minutes INTEGER,
                sharpe_ratio DECIMAL(10, 4),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')

        # 인덱스 생성
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_candles_market_time
            ON candles(market, timeframe, timestamp DESC)
        ''')

        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trades_timestamp
            ON trades(timestamp DESC)
        ''')

        self.conn.commit()
        print("✅ 테이블 생성 완료")

    def save_candles(self, market, timeframe, candles):
        """
        캔들 데이터 저장

        Args:
            market: 마켓 (KRW-BTC 등)
            timeframe: 타임프레임 (1m, 5m, 15m, 1h, 4h, 1d)
            candles: 업비트 API 캔들 리스트
        """
        saved = 0
        for candle in candles:
            try:
                timestamp = candle.get('candle_date_time_kst') or candle.get('candle_date_time_utc')

                self.cursor.execute('''
                    INSERT OR IGNORE INTO candles
                    (market, timeframe, timestamp, open_price, high_price,
                     low_price, close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    market,
                    timeframe,
                    timestamp,
                    candle['opening_price'],
                    candle['high_price'],
                    candle['low_price'],
                    candle['trade_price'],
                    candle['candle_acc_trade_volume']
                ))

                if self.cursor.rowcount > 0:
                    saved += 1

            except Exception as e:
                print(f"캔들 저장 실패: {e}")
                continue

        self.conn.commit()
        return saved

    def get_candles(self, market, timeframe, days=30):
        """
        저장된 캔들 데이터 조회

        Returns:
            업비트 API 형식과 동일한 리스트
        """
        cutoff = datetime.now() - timedelta(days=days)

        self.cursor.execute('''
            SELECT timestamp, open_price, high_price, low_price,
                   close_price, volume
            FROM candles
            WHERE market = ? AND timeframe = ? AND timestamp >= ?
            ORDER BY timestamp DESC
        ''', (market, timeframe, cutoff.strftime('%Y-%m-%d %H:%M:%S')))

        rows = self.cursor.fetchall()

        # 업비트 API 형식으로 변환
        candles = []
        for row in rows:
            candles.append({
                'candle_date_time_kst': row[0],
                'opening_price': float(row[1]),
                'high_price': float(row[2]),
                'low_price': float(row[3]),
                'trade_price': float(row[4]),
                'candle_acc_trade_volume': float(row[5])
            })

        return candles

    def save_trade(self, trade_data):
        """거래 기록 저장"""
        self.cursor.execute('''
            INSERT INTO trades
            (market, trade_type, price, amount, krw_amount, profit,
             profit_rate, reason, hold_time_minutes, peak_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get('market'),
            trade_data.get('type'),  # BUY or SELL
            trade_data.get('price'),
            trade_data.get('amount'),
            trade_data.get('krw_amount'),
            trade_data.get('profit', 0),
            trade_data.get('profit_rate', 0),
            trade_data.get('reason', ''),
            trade_data.get('hold_time_minutes', 0),
            trade_data.get('peak_profit', 0)
        ))

        self.conn.commit()

    def save_optimization_result(self, market, params, backtest_result):
        """파라미터 최적화 결과 저장"""

        # 기존 active 파라미터 비활성화
        self.cursor.execute('''
            UPDATE parameter_history
            SET is_active = 0
            WHERE market = ? AND is_active = 1
        ''', (market,))

        # 새 파라미터 저장
        self.cursor.execute('''
            INSERT INTO parameter_history
            (market, optimization_date, quick_profit, take_profit_1,
             take_profit_2, stop_loss, trailing_stop_tight,
             trailing_stop_medium, trailing_stop_wide,
             backtest_return, backtest_winrate, backtest_sharpe, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            market,
            datetime.now(),
            params.get('quick_profit'),
            params.get('take_profit_1'),
            params.get('take_profit_2', 0.025),
            params.get('stop_loss'),
            params.get('trailing_stop_tight'),
            params.get('trailing_stop_medium', 0.005),
            params.get('trailing_stop_wide', 0.008),
            backtest_result.get('total_return'),
            backtest_result.get('win_rate'),
            backtest_result.get('sharpe_ratio'),
            backtest_result.get('score')
        ))

        self.conn.commit()

    def get_active_parameters(self, market):
        """현재 활성화된 최적 파라미터 조회"""
        self.cursor.execute('''
            SELECT quick_profit, take_profit_1, take_profit_2, stop_loss,
                   trailing_stop_tight, trailing_stop_medium, trailing_stop_wide,
                   optimization_date
            FROM parameter_history
            WHERE market = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
        ''', (market,))

        row = self.cursor.fetchone()

        if row:
            return {
                'quick_profit': float(row[0]),
                'take_profit_1': float(row[1]),
                'take_profit_2': float(row[2]),
                'stop_loss': float(row[3]),
                'trailing_stop_tight': float(row[4]),
                'trailing_stop_medium': float(row[5]),
                'trailing_stop_wide': float(row[6]),
                'last_optimized': row[7]
            }

        return None

    def update_daily_performance(self, date=None):
        """일일 성과 집계"""
        if date is None:
            date = datetime.now().date()

        # 해당 날짜의 거래 집계
        self.cursor.execute('''
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(profit) as total_profit,
                MAX(profit) as best_trade,
                MIN(profit) as worst_trade,
                AVG(hold_time_minutes) as avg_hold_time
            FROM trades
            WHERE DATE(timestamp) = ? AND trade_type = 'SELL'
        ''', (date,))

        row = self.cursor.fetchone()

        if row and row[0] > 0:
            total_trades = row[0]
            winning_trades = row[1] or 0
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            self.cursor.execute('''
                INSERT OR REPLACE INTO daily_performance
                (date, total_trades, winning_trades, win_rate, total_profit,
                 best_trade, worst_trade, avg_hold_time_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                total_trades,
                winning_trades,
                win_rate,
                row[2] or 0,
                row[3] or 0,
                row[4] or 0,
                int(row[5] or 0)
            ))

            self.conn.commit()
            return True

        return False

    def get_performance_report(self, days=30):
        """성과 리포트 조회"""
        cutoff = datetime.now().date() - timedelta(days=days)

        self.cursor.execute('''
            SELECT date, total_trades, win_rate, total_profit
            FROM daily_performance
            WHERE date >= ?
            ORDER BY date DESC
        ''', (cutoff,))

        return self.cursor.fetchall()

    def close(self):
        """연결 종료"""
        self.conn.close()


if __name__ == "__main__":
    """테스트"""

    # SQLite로 테스트
    db = DatabaseManager(use_oracle=False)

    print("\n=== 테이블 생성 테스트 ===")
    print("✅ 완료")

    # 테스트 데이터 저장
    print("\n=== 거래 기록 저장 테스트 ===")
    test_trade = {
        'market': 'KRW-BTC',
        'type': 'SELL',
        'price': 50000000,
        'amount': 0.001,
        'krw_amount': 50000,
        'profit': 1000,
        'profit_rate': 0.02,
        'reason': '익절',
        'hold_time_minutes': 30,
        'peak_profit': 0.025
    }

    db.save_trade(test_trade)
    print("✅ 거래 기록 저장 완료")

    # 파라미터 저장 테스트
    print("\n=== 파라미터 최적화 결과 저장 테스트 ===")
    test_params = {
        'quick_profit': 0.008,
        'take_profit_1': 0.015,
        'take_profit_2': 0.025,
        'stop_loss': -0.015,
        'trailing_stop_tight': 0.003,
        'trailing_stop_medium': 0.005,
        'trailing_stop_wide': 0.008
    }

    test_result = {
        'total_return': 15.5,
        'win_rate': 68.5,
        'sharpe_ratio': 1.25,
        'score': 85.3
    }

    db.save_optimization_result('KRW-BTC', test_params, test_result)
    print("✅ 최적화 결과 저장 완료")

    # 조회 테스트
    print("\n=== 활성 파라미터 조회 테스트 ===")
    active_params = db.get_active_parameters('KRW-BTC')
    if active_params:
        print("활성 파라미터:")
        for key, value in active_params.items():
            print(f"  {key}: {value}")

    # 일일 성과 집계
    print("\n=== 일일 성과 집계 테스트 ===")
    db.update_daily_performance()
    print("✅ 성과 집계 완료")

    db.close()
    print("\n✅ 모든 테스트 완료")
