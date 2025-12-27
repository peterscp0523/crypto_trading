"""
백테스팅 스크립트
실제 과거 데이터로 전략 테스트
"""
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators


class Backtester:
    """백테스팅 엔진"""

    def __init__(self, upbit, market="KRW-ETH"):
        self.upbit = upbit
        self.market = market

        # 전략 파라미터 (telegram_bot.py와 동일)
        self.rsi_buy = 35
        self.rsi_sell = 70
        self.take_profit = 0.03      # 5% → 3%
        self.stop_loss = -0.02       # -3% → -2%
        self.trailing_stop = 0.015   # 트레일링 스톱 -1.5%
        self.volume_threshold = 1.2

        # 백테스트 결과
        self.trades = []
        self.position = None
        self.position_peak_profit = 0

    def get_trend_analysis(self, prices_1h, prices_4h):
        """다중 시간대 추세 분석"""
        try:
            if len(prices_1h) < 50 or len(prices_4h) < 50:
                return None

            # 1시간 추세
            rsi_1h = TechnicalIndicators.calculate_rsi(prices_1h, 14)
            ma20_1h = sum(prices_1h[:20]) / 20
            ma50_1h = sum(prices_1h[:50]) / 50
            trend_1h = "up" if ma20_1h > ma50_1h and prices_1h[0] > ma20_1h else "down"

            # 4시간 추세
            rsi_4h = TechnicalIndicators.calculate_rsi(prices_4h, 14)
            ma20_4h = sum(prices_4h[:20]) / 20
            ma50_4h = sum(prices_4h[:50]) / 50
            trend_4h = "up" if ma20_4h > ma50_4h and prices_4h[0] > ma20_4h else "down"

            # 추세 상태 판단 (RSI 기준 완화)
            if trend_1h == "up" and trend_4h == "up":
                trend_state = "strong_bull"
                buy_allowed = True
                rsi_threshold = 50  # 40 → 50
            elif trend_1h == "down" and trend_4h == "up":
                trend_state = "correction"
                buy_allowed = True
                rsi_threshold = 45  # 35 → 45
            elif trend_1h == "up" and trend_4h == "down":
                trend_state = "weak_bounce"
                buy_allowed = True
                rsi_threshold = 40  # 30 → 40
            else:
                trend_state = "strong_bear"
                buy_allowed = True  # False → True (하락장에서도 매수)
                rsi_threshold = 30  # 25 → 30

            return {
                'trend_1h': trend_1h,
                'trend_4h': trend_4h,
                'rsi_1h': rsi_1h,
                'rsi_4h': rsi_4h,
                'trend_state': trend_state,
                'buy_allowed': buy_allowed,
                'rsi_threshold': rsi_threshold
            }
        except:
            return None

    def get_signals(self, prices, volumes, prices_1h, prices_4h):
        """매매 신호 생성"""
        if len(prices) < 20 or len(volumes) < 20:
            return None

        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        upper, middle, lower = AdvancedIndicators.calculate_bollinger_bands(prices, 20, 2)
        vol_ma = AdvancedIndicators.calculate_volume_ma(volumes, 20)

        if not all([rsi, upper, lower, vol_ma]):
            return None

        current_price = prices[0]
        current_vol = volumes[0]

        # 추세 분석
        trend = self.get_trend_analysis(prices_1h, prices_4h)

        # 매수 조건 (완화됨 - 거래량 조건 제거/완화)
        buy_signal = False
        if trend and trend['buy_allowed']:
            rsi_threshold = trend['rsi_threshold']

            if trend['trend_state'] == 'strong_bull':
                # 강한 상승: RSI만 체크
                buy_signal = (rsi < rsi_threshold)
            elif trend['trend_state'] == 'correction':
                # 조정: RSI + 볼린저 완화
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.05)
            elif trend['trend_state'] == 'weak_bounce':
                # 약한 반등: RSI + 볼린저
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.03)
            elif trend['trend_state'] == 'strong_bear':
                # 강한 하락: 과매도 + 볼린저 하단
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.02)
        else:
            # 추세 분석 실패: 극도의 과매도만
            buy_signal = (rsi < 25 and current_price <= lower * 1.01)

        return {
            'price': current_price,
            'rsi': rsi,
            'upper': upper,
            'lower': lower,
            'vol_ratio': current_vol / vol_ma,
            'trend': trend,
            'buy': buy_signal,
            'sell': rsi > self.rsi_sell and current_price >= upper * 0.99
        }

    def run(self, days=7, initial_balance=1000000, debug=False, timeframe="15m"):
        """백테스트 실행

        Args:
            timeframe: "5m" (약 17시간), "15m" (2일), "1h" (8일)
        """
        print(f"\n{'='*60}")
        print(f"백테스트 시작: {self.market}")
        print(f"타임프레임: {timeframe}")
        print(f"초기 자금: {initial_balance:,}원")
        print(f"{'='*60}\n")

        balance = initial_balance
        total_trades = 0
        wins = 0
        losses = 0
        check_count = 0
        buy_checks = []

        # 데이터 로딩 (업비트 API 제한: 200개)
        print("데이터 로딩 중...")

        if timeframe == "1h":
            # 1시간봉 백테스트 (약 8일)
            candles_main = self.upbit.get_candles(self.market, "minutes", 60, 200)
            candles_1h = candles_main
            candles_4h = self.upbit.get_candles(self.market, "minutes", 240, 200)
            main_label = "1시간봉"
        elif timeframe == "5m":
            # 5분봉 백테스트 (약 17시간)
            candles_main = self.upbit.get_candles(self.market, "minutes", 5, 200)
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 200)
            candles_4h = self.upbit.get_candles(self.market, "minutes", 240, 200)
            main_label = "5분봉"
        else:
            # 15분봉 백테스트 (약 2일)
            candles_main = self.upbit.get_candles(self.market, "minutes", 15, 200)
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 200)
            candles_4h = self.upbit.get_candles(self.market, "minutes", 240, 200)
            main_label = "15분봉"

        candles_15m = candles_main  # 호환성을 위해

        if len(candles_15m) < 100:
            print("❌ 데이터 부족")
            return

        if timeframe == "1h":
            days_covered = len(candles_main) / 24
        elif timeframe == "5m":
            days_covered = len(candles_main) / 288  # 하루 = 288개 (24*12)
        else:
            days_covered = len(candles_main) / 96

        print(f"✅ {main_label}: {len(candles_main)}개 (약 {days_covered:.1f}일)")
        print(f"✅ 1시간봉: {len(candles_1h)}개")
        print(f"✅ 4시간봉: {len(candles_4h)}개\n")

        # 역순으로 정렬 (과거 -> 현재)
        candles_15m.reverse()
        candles_1h.reverse()
        candles_4h.reverse()

        # 백테스트 시작 인덱스 (충분한 데이터 확보 후 시작)
        start_idx = 50  # 최소 50개 데이터만 있으면 시작

        print(f"백테스트 범위: {start_idx}번째 ~ {len(candles_15m)}번째 캔들")
        print(f"예상 반복 횟수: {len(candles_15m) - start_idx}회\n")

        # 디버그 카운터
        loop_count = 0
        skip_data = 0
        skip_signal = 0

        # 시뮬레이션
        for i in range(start_idx, len(candles_15m)):
            loop_count += 1

            # 현재 시점의 데이터 (최근 50개)
            window_15m = candles_15m[max(0, i-50):i]
            window_1h = candles_1h[max(0, i-200):i]
            window_4h = candles_4h[max(0, i-200):i]

            if len(window_15m) < 20 or len(window_1h) < 50 or len(window_4h) < 50:
                skip_data += 1
                if debug and skip_data == 1:
                    print(f"[디버그] 데이터 부족으로 스킵: 15m={len(window_15m)}, 1h={len(window_1h)}, 4h={len(window_4h)}")
                continue

            # 가격/거래량 추출 (최신 데이터가 앞에 오도록 역순)
            prices_15m = [c['trade_price'] for c in reversed(window_15m)]
            volumes_15m = [c['candle_acc_trade_volume'] for c in reversed(window_15m)]
            prices_1h = [c['trade_price'] for c in reversed(window_1h)]
            prices_4h = [c['trade_price'] for c in reversed(window_4h)]

            signals = self.get_signals(prices_15m, volumes_15m, prices_1h, prices_4h)

            if not signals:
                skip_signal += 1
                if debug and skip_signal == 1:
                    print(f"[디버그] 신호 생성 실패로 스킵")
                continue

            current_candle = candles_15m[i]
            current_time = current_candle['candle_date_time_kst']
            price = signals['price']

            # 포지션 있을 때
            if self.position:
                buy_price = self.position['buy_price']
                profit_rate = (price - buy_price) / buy_price

                # 최고 수익률 업데이트
                if profit_rate > self.position_peak_profit:
                    self.position_peak_profit = profit_rate

                # 익절
                if profit_rate >= self.take_profit:
                    sell_value = balance * (1 + profit_rate)
                    profit = sell_value - balance

                    self.trades.append({
                        'type': 'SELL',
                        'time': current_time,
                        'buy_price': buy_price,
                        'sell_price': price,
                        'profit': profit,
                        'profit_rate': profit_rate * 100,
                        'reason': '익절'
                    })

                    balance = sell_value
                    total_trades += 1
                    wins += 1

                    print(f"[{current_time}] 🟢 익절: {buy_price:,.0f} → {price:,.0f} ({profit_rate*100:+.2f}%) 잔고: {balance:,.0f}원")
                    self.position = None
                    self.position_peak_profit = 0

                # 손절
                elif profit_rate <= self.stop_loss:
                    sell_value = balance * (1 + profit_rate)
                    profit = sell_value - balance

                    self.trades.append({
                        'type': 'SELL',
                        'time': current_time,
                        'buy_price': buy_price,
                        'sell_price': price,
                        'profit': profit,
                        'profit_rate': profit_rate * 100,
                        'reason': '손절'
                    })

                    balance = sell_value
                    total_trades += 1
                    losses += 1

                    print(f"[{current_time}] 🔴 손절: {buy_price:,.0f} → {price:,.0f} ({profit_rate*100:+.2f}%) 잔고: {balance:,.0f}원")
                    self.position = None
                    self.position_peak_profit = 0

                # 트레일링 스톱 (최고점 대비 -1.5% 하락)
                elif self.position_peak_profit > 0.01 and profit_rate < self.position_peak_profit - self.trailing_stop:
                    sell_value = balance * (1 + profit_rate)
                    profit = sell_value - balance

                    self.trades.append({
                        'type': 'SELL',
                        'time': current_time,
                        'buy_price': buy_price,
                        'sell_price': price,
                        'profit': profit,
                        'profit_rate': profit_rate * 100,
                        'reason': f'트레일링스톱 (최고:{self.position_peak_profit*100:.2f}%)'
                    })

                    balance = sell_value
                    total_trades += 1
                    if profit > 0:
                        wins += 1
                    else:
                        losses += 1

                    print(f"[{current_time}] 🟡 트레일링: {buy_price:,.0f} → {price:,.0f} ({profit_rate*100:+.2f}%, 최고:{self.position_peak_profit*100:.2f}%) 잔고: {balance:,.0f}원")
                    self.position = None
                    self.position_peak_profit = 0

                # RSI 매도
                elif signals['sell']:
                    sell_value = balance * (1 + profit_rate)
                    profit = sell_value - balance

                    self.trades.append({
                        'type': 'SELL',
                        'time': current_time,
                        'buy_price': buy_price,
                        'sell_price': price,
                        'profit': profit,
                        'profit_rate': profit_rate * 100,
                        'reason': 'RSI매도'
                    })

                    balance = sell_value
                    total_trades += 1
                    if profit > 0:
                        wins += 1
                    else:
                        losses += 1

                    print(f"[{current_time}] 🟡 매도: {buy_price:,.0f} → {price:,.0f} ({profit_rate*100:+.2f}%) 잔고: {balance:,.0f}원")
                    self.position = None
                    self.position_peak_profit = 0

            # 포지션 없을 때
            else:
                check_count += 1

                # 디버그: 매수 조건 체크
                if debug and check_count % 20 == 0:  # 20번마다 한 번씩 출력
                    trend = signals.get('trend')
                    if trend:
                        # 볼린저 밴드 위치 계산
                        bb_pos = ((price - signals['lower']) / (signals['upper'] - signals['lower'])) * 100 if signals['upper'] > signals['lower'] else 50
                        print(f"\n[디버그 {check_count}] {current_time}")
                        print(f"  추세: {trend['trend_state']} (1H:{trend['trend_1h']}, 4H:{trend['trend_4h']})")
                        print(f"  RSI: {signals['rsi']:.1f} (기준: {trend['rsi_threshold']})")
                        print(f"  거래량: {signals['vol_ratio']:.2f}x")
                        print(f"  볼린저: {bb_pos:.1f}%")
                        print(f"  매수신호: {signals['buy']}")

                if signals['buy'] and balance >= 5000:
                    self.position = {
                        'buy_price': price,
                        'buy_time': current_time,
                        'balance': balance
                    }

                    trend_info = ""
                    if signals.get('trend'):
                        trend = signals['trend']
                        trend_name = {"strong_bull": "🚀강한상승", "correction": "📊조정", "weak_bounce": "⚡약한반등"}
                        trend_info = f" {trend_name.get(trend['trend_state'], '?')}"

                    print(f"\n[{current_time}] 🔵 매수: {price:,.0f}원 RSI:{signals['rsi']:.1f}{trend_info}")
                else:
                    # 매수 실패 이유 기록
                    if signals['buy']:
                        buy_checks.append({
                            'time': current_time,
                            'rsi': signals['rsi'],
                            'vol_ratio': signals['vol_ratio'],
                            'trend': signals.get('trend', {}).get('trend_state'),
                            'reason': '잔고부족' if balance < 5000 else '신호있음'
                        })

        # 결과 리포트
        print(f"\n{'='*60}")
        print("백테스트 결과")
        print(f"{'='*60}")
        print(f"초기 자금: {initial_balance:,}원")
        print(f"최종 잔고: {balance:,.0f}원")
        print(f"총 손익: {balance - initial_balance:+,.0f}원 ({(balance/initial_balance - 1)*100:+.2f}%)")
        print(f"\n루프 실행: {loop_count}회")
        print(f"데이터 부족 스킵: {skip_data}회")
        print(f"신호 생성 실패 스킵: {skip_signal}회")
        print(f"분석 횟수: {check_count}회")
        print(f"거래 횟수: {total_trades}회")
        print(f"승리: {wins}회")
        print(f"패배: {losses}회")

        if debug:
            print(f"\n매수 신호 발생: {len(buy_checks)}회")
            if buy_checks:
                print("최근 매수 신호:")
                for check in buy_checks[-3:]:
                    print(f"  {check['time']}: RSI {check['rsi']:.1f}, 거래량 {check['vol_ratio']:.2f}x, {check['trend']}")

        if total_trades > 0:
            win_rate = wins / total_trades * 100
            print(f"승률: {win_rate:.1f}%")

            profits = [t['profit'] for t in self.trades if t['profit'] > 0]
            losses_amt = [t['profit'] for t in self.trades if t['profit'] < 0]

            if profits:
                print(f"\n평균 수익: {sum(profits)/len(profits):+,.0f}원")
                print(f"최대 수익: {max(profits):+,.0f}원")

            if losses_amt:
                print(f"평균 손실: {sum(losses_amt)/len(losses_amt):+,.0f}원")
                print(f"최대 손실: {min(losses_amt):+,.0f}원")

        print(f"{'='*60}\n")

        return {
            'initial': initial_balance,
            'final': balance,
            'profit': balance - initial_balance,
            'profit_rate': (balance/initial_balance - 1) * 100,
            'trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': wins / total_trades * 100 if total_trades > 0 else 0
        }


if __name__ == "__main__":
    from config import get_config

    try:
        # .env 파일에서 설정 로드
        config = get_config()

        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])

        # 백테스트 실행 (1시간봉으로 8일치 데이터)
        backtester = Backtester(upbit, config['market'])
        result = backtester.run(initial_balance=1000000, debug=True, timeframe="1h")

    except Exception as e:
        print(f"❌ 백테스트 실패: {e}")
        print("\n.env 파일을 확인해주세요.")
