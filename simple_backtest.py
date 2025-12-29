"""
간단한 백테스팅 도구

업비트 과거 데이터로 전략 성능 검증
pandas 사용
"""
import pandas as pd
from datetime import datetime
from upbit_api import UpbitAPI
from config import get_config
import time


class SimpleBacktester:
    """간단한 백테스팅 엔진"""

    def __init__(self, upbit_api, initial_balance=1000000):
        self.upbit = upbit_api
        self.initial_balance = initial_balance
        self.reset()

    def reset(self):
        """상태 초기화"""
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.position_peak = 0

    def fetch_data(self, market, days=30):
        """
        과거 데이터 수집 (1시간봉)

        Args:
            market: 마켓 코드 (e.g., 'KRW-BTC')
            days: 수집 일수

        Returns:
            DataFrame
        """
        print(f"\n📊 {market} 과거 {days}일 데이터 수집...")

        all_candles = []
        total_hours = days * 24

        # 200개씩 요청
        for offset in range(0, total_hours, 200):
            count = min(200, total_hours - offset)
            candles = self.upbit.get_candles(market, "minutes", 60, count)

            if not candles:
                break

            all_candles.extend(candles)
            print(f"   수집 중... {len(all_candles)}/{total_hours}")

            time.sleep(0.1)  # API 제한

        if not all_candles:
            return None

        # DataFrame 변환
        df = pd.DataFrame(all_candles)
        df['timestamp'] = pd.to_datetime(df['candle_date_time_kst'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # 컬럼 정리
        df = df.rename(columns={
            'opening_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'trade_price': 'close',
            'candle_acc_trade_volume': 'volume'
        })

        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        print(f"✅ {len(df)}개 캔들 수집 완료")
        print(f"   {df['timestamp'].min()} ~ {df['timestamp'].max()}")

        return df

    def calculate_indicators(self, df):
        """기술적 지표 계산"""
        # RSI
        df['rsi'] = self._calc_rsi(df['close'], 14)

        # 볼린저 밴드
        df['bb_middle'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_middle'] - (2 * df['bb_std'])
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 이동평균
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma50'] = df['close'].rolling(50).mean()

        return df

    def _calc_rsi(self, prices, period=14):
        """RSI 계산"""
        deltas = prices.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = -deltas.where(deltas < 0, 0)

        avg_gain = gains.rolling(window=period).mean()
        avg_loss = losses.rolling(window=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def check_buy_signal(self, row):
        """매수 신호 체크"""
        # RSI 30-40 과매도
        if not (30 <= row['rsi'] <= 40):
            return False

        # BB 하단 20% 이내
        if not (row['bb_position'] <= 0.2):
            return False

        return True

    def check_sell_signal(self, row, position):
        """매도 신호 체크"""
        if not position:
            return False, None

        buy_price = position['buy_price']
        profit_pct = ((row['close'] - buy_price) / buy_price) * 100

        # 피크 추적
        if profit_pct > self.position_peak:
            self.position_peak = profit_pct

        # 1. 목표 달성 (1.5%)
        if profit_pct >= 1.5:
            return True, f"목표 달성 ({profit_pct:.2f}%)"

        # 2. 기본 익절 (1.0%)
        if profit_pct >= 1.0:
            return True, f"익절 ({profit_pct:.2f}%)"

        # 3. 트레일링 스톱
        if self.position_peak >= 1.2 and (self.position_peak - profit_pct) >= 0.4:
            return True, f"트레일링 ({self.position_peak:.2f}% → {profit_pct:.2f}%)"

        # 4. 손절 (-0.6%)
        if profit_pct <= -0.6:
            return True, f"손절 ({profit_pct:.2f}%)"

        # 5. 시간 초과 (3시간 = 3개 캔들)
        hold_hours = (row.name - position['buy_index'])
        if hold_hours >= 3:
            return True, f"시간 초과 ({hold_hours}h, {profit_pct:.2f}%)"

        return False, None

    def run(self, df):
        """백테스팅 실행"""
        print(f"\n🔄 백테스팅 시작")
        print(f"   초기 자본: {self.initial_balance:,.0f}원")
        print(f"   데이터: {len(df)}개 캔들")

        self.reset()

        for idx, row in df.iterrows():
            if idx < 50:  # 지표 계산 최소 데이터
                continue

            # 매수 체크
            if self.position is None and self.balance >= 5000:
                if self.check_buy_signal(row):
                    invest = int(self.balance * 0.8)
                    fee = invest * 0.0005
                    buy_price = row['close']
                    amount = (invest - fee) / buy_price

                    self.position = {
                        'buy_index': idx,
                        'buy_time': row['timestamp'],
                        'buy_price': buy_price,
                        'amount': amount,
                        'invest': invest
                    }
                    self.balance -= invest
                    self.position_peak = 0

                    print(f"  💰 [{row['timestamp']}] 매수: {buy_price:,.0f}원")

            # 매도 체크
            elif self.position is not None:
                should_sell, reason = self.check_sell_signal(row, self.position)

                if should_sell:
                    sell_price = row['close']
                    sell_value = self.position['amount'] * sell_price
                    fee = sell_value * 0.0005
                    final_value = sell_value - fee

                    profit = final_value - self.position['invest']
                    profit_pct = (profit / self.position['invest']) * 100

                    self.balance += final_value

                    self.trades.append({
                        'buy_time': self.position['buy_time'],
                        'sell_time': row['timestamp'],
                        'buy_price': self.position['buy_price'],
                        'sell_price': sell_price,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'reason': reason
                    })

                    print(f"  💸 [{row['timestamp']}] 매도: {sell_price:,.0f}원 ({profit:+,.0f}원, {profit_pct:+.2f}%) - {reason}")

                    self.position = None

        # 미체결 포지션 정리
        if self.position:
            final_row = df.iloc[-1]
            final_value = self.position['amount'] * final_row['close']
            self.balance += final_value
            print(f"\n  ⚠️ 미체결 포지션 강제 청산: {final_value:,.0f}원")

        return self.analyze()

    def analyze(self):
        """결과 분석"""
        if not self.trades:
            return {
                'total_trades': 0,
                'final_balance': self.balance,
                'total_return': 0,
                'total_return_pct': 0
            }

        total_trades = len(self.trades)
        winning = sum(1 for t in self.trades if t['profit'] > 0)
        win_rate = (winning / total_trades) * 100

        total_return = self.balance - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        avg_profit = sum(t['profit'] for t in self.trades) / total_trades
        avg_profit_pct = sum(t['profit_pct'] for t in self.trades) / total_trades

        return {
            'total_trades': total_trades,
            'winning_trades': winning,
            'losing_trades': total_trades - winning,
            'win_rate': win_rate,
            'final_balance': self.balance,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'avg_profit': avg_profit,
            'avg_profit_pct': avg_profit_pct,
            'max_profit': max(t['profit'] for t in self.trades),
            'max_loss': min(t['profit'] for t in self.trades),
            'trades': self.trades
        }

    def print_results(self, results):
        """결과 출력"""
        print("\n" + "=" * 70)
        print("📊 백테스팅 결과")
        print("=" * 70)
        print(f"총 거래: {results['total_trades']}회")
        print(f"승리: {results['winning_trades']}회 | 패배: {results['losing_trades']}회")
        print(f"승률: {results['win_rate']:.1f}%")
        print()
        print(f"초기 자본: {self.initial_balance:,.0f}원")
        print(f"최종 자본: {results['final_balance']:,.0f}원")
        print(f"총 수익: {results['total_return']:+,.0f}원 ({results['total_return_pct']:+.2f}%)")
        print()
        print(f"평균 수익: {results['avg_profit']:+,.0f}원 ({results['avg_profit_pct']:+.2f}%)")
        print(f"최대 수익: {results['max_profit']:+,.0f}원")
        print(f"최대 손실: {results['max_loss']:+,.0f}원")
        print("=" * 70)

        # 거래별 상세
        if results['trades']:
            print("\n📝 거래 내역:")
            for i, trade in enumerate(results['trades'], 1):
                print(f"  {i}. {trade['buy_time']} → {trade['sell_time']}")
                print(f"     {trade['buy_price']:,.0f}원 → {trade['sell_price']:,.0f}원 "
                      f"({trade['profit']:+,.0f}원, {trade['profit_pct']:+.2f}%) - {trade['reason']}")


if __name__ == "__main__":
    print("=" * 70)
    print("📊 백테스팅 도구 (BTC 보수적 전략)")
    print("=" * 70)

    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

    # 백테스터 생성
    backtester = SimpleBacktester(upbit, initial_balance=1_000_000)

    # 데이터 수집
    df = backtester.fetch_data("KRW-BTC", days=30)

    if df is not None:
        # 지표 계산
        df = backtester.calculate_indicators(df)

        # 백테스팅 실행
        results = backtester.run(df)

        # 결과 출력
        backtester.print_results(results)

        # CSV 저장
        if results['trades']:
            trades_df = pd.DataFrame(results['trades'])
            trades_df.to_csv('backtest_results.csv', index=False, encoding='utf-8-sig')
            print(f"\n💾 거래 내역 저장: backtest_results.csv")
