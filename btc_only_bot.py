"""
비트코인 전용 보수적 트레이딩 봇

대장 코인만 거래 → 안정성 극대화
"""
import os
import time
from datetime import datetime
from upbit_api import UpbitAPI
from config import get_config


class SimpleTelegramBot:
    """간단한 텔레그램 봇"""

    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.last_update_id = 0

    def send_message(self, text):
        """메시지 전송"""
        try:
            import requests
            url = f"{self.base_url}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            response = requests.post(url, data=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"텔레그램 전송 실패: {e}")
            return None

    def get_updates(self):
        """새 메시지 확인"""
        try:
            import requests
            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 1}
            response = requests.get(url, params=params, timeout=3)
            result = response.json()

            if result.get("ok") and result.get("result"):
                updates = result["result"]
                if updates:
                    self.last_update_id = updates[-1]["update_id"]
                    return updates
            return []
        except Exception:
            return []

    def check_command(self):
        """명령어 체크"""
        updates = self.get_updates()
        for update in updates:
            if "message" in update and "text" in update["message"]:
                text = update["message"]["text"].strip().lower()
                return text
        return None


class BitcoinOnlyBot:
    """비트코인 전용 봇"""

    def __init__(self, upbit, telegram):
        self.upbit = upbit
        self.telegram = telegram
        self.market = "KRW-BTC"

        # 포지션
        self.position = None
        self.position_peak = 0

        # 통계
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0

    def log(self, msg):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    def get_balance(self):
        """잔고 조회"""
        accounts = self.upbit.get_accounts()
        krw = 0
        btc_balance = 0
        btc_avg_price = 0

        for acc in accounts:
            currency = acc['currency']
            balance = float(acc['balance'])

            if currency == 'KRW':
                krw = balance
            elif currency == 'BTC' and balance > 0:
                btc_balance = balance
                btc_avg_price = float(acc['avg_buy_price'])

        return krw, btc_balance, btc_avg_price

    def check_buy_signal(self):
        """
        비트코인 매수 신호 (매우 보수적)

        조건:
        1. RSI 30-40 (과매도)
        2. 볼린저 밴드 하단 20% 이내
        3. 1시간 봉 하락 추세 (반등 준비)
        """
        try:
            # 1분봉 30개
            candles_1m = self.upbit.get_candles(self.market, "minutes", 1, 30)
            # 1시간봉 24개
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 24)

            if not candles_1m or not candles_1h:
                return None

            # RSI 계산
            rsi = self._calculate_rsi(candles_1m, period=14)
            if rsi is None or not (30 <= rsi <= 40):
                return None

            # 볼린저 밴드 위치
            bb_position = self._calculate_bb_position(candles_1m, period=20)
            if bb_position is None or bb_position > 0.2:
                return None

            # 1시간 추세 (하락 중)
            change_1h = ((candles_1h[0]['trade_price'] - candles_1h[5]['trade_price'])
                        / candles_1h[5]['trade_price']) * 100

            if change_1h > -1.0:  # 최소 -1% 하락
                return None

            current_price = candles_1m[0]['trade_price']

            return {
                'action': 'buy',
                'reason': f'BTC 반등 신호 (RSI {rsi:.0f}, BB하단, 1h {change_1h:.1f}%)',
                'price': current_price,
                'confidence': 0.8
            }

        except Exception as e:
            self.log(f"❌ 매수 신호 체크 실패: {e}")
            return None

    def _calculate_rsi(self, candles, period=14):
        """RSI 계산"""
        if len(candles) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(period):
            change = candles[i]['trade_price'] - candles[i+1]['trade_price']
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_bb_position(self, candles, period=20):
        """볼린저 밴드 내 위치"""
        if len(candles) < period:
            return None

        prices = [c['trade_price'] for c in candles[:period]]
        current_price = candles[0]['trade_price']

        mean = sum(prices) / period
        variance = sum((p - mean) ** 2 for p in prices) / period
        std = variance ** 0.5

        upper_band = mean + (2 * std)
        lower_band = mean - (2 * std)

        if upper_band == lower_band:
            return 0.5

        position = (current_price - lower_band) / (upper_band - lower_band)
        return max(0.0, min(1.0, position))

    def check_sell_signal(self, current_price):
        """매도 신호 체크"""
        if not self.position:
            return None

        buy_price = self.position['buy_price']
        buy_time = self.position['buy_time']

        profit_pct = ((current_price - buy_price) / buy_price) * 100
        hold_minutes = (datetime.now() - buy_time).total_seconds() / 60

        # 피크 추적
        if profit_pct > self.position_peak:
            self.position_peak = profit_pct

        # 1. 목표 달성 (1.5%)
        if profit_pct >= 1.5:
            return {
                'reason': f'목표 달성 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 2. 기본 익절 (1.0%)
        if profit_pct >= 1.0:
            return {
                'reason': f'익절 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 3. 트레일링 스톱 (1.2% 이상 수익 시)
        if self.position_peak >= 1.2 and (self.position_peak - profit_pct) >= 0.4:
            return {
                'reason': f'트레일링 스톱 (피크 {self.position_peak:.2f}% → {profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 4. 시간 초과 (3시간 = 180분)
        if hold_minutes > 180:
            return {
                'reason': f'시간 초과 ({hold_minutes:.0f}분, {profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 5. 손절 (-0.6%)
        if profit_pct <= -0.6:
            return {
                'reason': f'손절 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        return None

    def execute_buy(self, signal):
        """매수 실행"""
        try:
            krw, btc_balance, _ = self.get_balance()

            # 80% 투자 (보수적)
            invest_krw = int(krw * 0.8)

            if invest_krw < 5000:
                self.log(f"⏸️ 잔고 부족: {krw:,.0f}원")
                return False

            self.log(f"💰 BTC 매수 시도: {invest_krw:,.0f}원")
            self.log(f"   사유: {signal['reason']}")

            result = self.upbit.order_market_buy(self.market, invest_krw)

            if result and 'uuid' in result:
                time.sleep(0.5)
                order_info = self.upbit.get_order(result['uuid'])

                if order_info and float(order_info.get('executed_volume', 0)) > 0:
                    trades = order_info.get('trades', [])
                    if trades:
                        total_funds = sum(float(t['funds']) for t in trades)
                        total_volume = sum(float(t['volume']) for t in trades)
                        executed_price = total_funds / total_volume
                        amount = total_volume
                    else:
                        executed_price = float(order_info.get('avg_price', 0))
                        amount = float(order_info.get('executed_volume', 0))

                    self.position = {
                        'market': self.market,
                        'buy_price': executed_price,
                        'buy_time': datetime.now(),
                        'amount': amount
                    }
                    self.position_peak = 0

                    self.log(f"✅ 매수 완료: {amount:.8f} BTC @ {executed_price:,.0f}원")

                    self.telegram.send_message(
                        f"💰 <b>BTC 매수 완료</b>\\n"
                        f"━━━━━━━━━━━━━━━━━\\n\\n"
                        f"수량: {amount:.8f} BTC\\n"
                        f"가격: {executed_price:,.0f}원\\n"
                        f"금액: {invest_krw:,.0f}원\\n\\n"
                        f"사유: {signal['reason']}\\n\\n"
                        f"🎯 목표: +1.0% / +1.5%\\n"
                        f"🛑 손절: -0.6%\\n"
                        f"⏱️  최대: 180분"
                    )
                    return True

            return False

        except Exception as e:
            self.log(f"❌ 매수 오류: {e}")
            return False

    def execute_sell(self, sell_signal):
        """매도 실행"""
        try:
            amount = self.position['amount']
            buy_price = self.position['buy_price']
            profit_pct = sell_signal['profit_pct']
            reason = sell_signal['reason']

            self.log(f"💸 BTC 매도 시도")
            self.log(f"   사유: {reason}")

            result = self.upbit.order_market_sell(self.market, amount)

            if result and 'uuid' in result:
                profit_krw = (amount * buy_price) * (profit_pct / 100)

                self.total_trades += 1
                self.total_pnl += profit_krw
                if profit_krw > 0:
                    self.winning_trades += 1

                win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

                self.log(f"✅ 매도 완료: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)")

                self.telegram.send_message(
                    f"💸 <b>BTC 매도 완료</b>\\n"
                    f"━━━━━━━━━━━━━━━━━\\n\\n"
                    f"수량: {amount:.8f} BTC\\n"
                    f"손익: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)\\n\\n"
                    f"사유: {reason}\\n\\n"
                    f"📊 <b>누적 통계</b>\\n"
                    f"총 거래: {self.total_trades}회\\n"
                    f"승률: {win_rate:.1f}%\\n"
                    f"총 손익: {self.total_pnl:+,.0f}원"
                )

                self.position = None
                self.position_peak = 0
                return True

            return False

        except Exception as e:
            self.log(f"❌ 매도 오류: {e}")
            return False

    def run(self, check_interval=120):
        """봇 실행 (120초 = 2분마다 체크)"""
        self.log("=" * 70)
        self.log("₿ 비트코인 전용 보수적 봇 시작")
        self.log("=" * 70)
        self.log(f"💰 대상: BTC만")
        self.log(f"🎯 매수: RSI 30-40 과매도 + BB하단")
        self.log(f"🎯 매도: 1.0% / 1.5%")
        self.log(f"🛑 손절: -0.6%")
        self.log(f"⏱️  최대: 180분")
        self.log(f"⏱️  체크: {check_interval}초마다")
        self.log("=" * 70)

        while True:
            try:
                # 텔레그램 명령어 체크
                command = self.telegram.check_command()
                if command:
                    if command in ['/stop', '/멈춰', '멈춰']:
                        self.log("🛑 봇 중지 명령")
                        self.telegram.send_message("🛑 <b>봇 중지</b>\\n\\n봇을 종료합니다.")
                        break
                    elif command in ['/status', '/상태']:
                        krw, btc_balance, btc_avg = self.get_balance()
                        if self.position:
                            ticker = self.upbit.get_current_price(self.market)
                            current_price = ticker['trade_price']
                            profit_pct = ((current_price - self.position['buy_price']) / self.position['buy_price']) * 100
                            hold_minutes = (datetime.now() - self.position['buy_time']).total_seconds() / 60

                            self.telegram.send_message(
                                f"📊 <b>BTC 봇 상태</b>\\n"
                                f"━━━━━━━━━━━━━━━━━\\n\\n"
                                f"💰 KRW: {krw:,.0f}원\\n"
                                f"₿ BTC: {btc_balance:.8f}\\n"
                                f"   매수가: {self.position['buy_price']:,.0f}원\\n"
                                f"   현재가: {current_price:,.0f}원\\n"
                                f"   수익률: {profit_pct:+.2f}%\\n"
                                f"   보유: {hold_minutes:.0f}분\\n\\n"
                                f"📊 총 {self.total_trades}회 | 승률 {(self.winning_trades/self.total_trades*100) if self.total_trades > 0 else 0:.1f}% | {self.total_pnl:+,.0f}원"
                            )
                        else:
                            self.telegram.send_message(
                                f"📊 <b>BTC 봇 상태</b>\\n"
                                f"━━━━━━━━━━━━━━━━━\\n\\n"
                                f"💰 KRW: {krw:,.0f}원\\n"
                                f"₿ BTC: {btc_balance:.8f}\\n"
                                f"📈 포지션: 없음 (신호 대기)\\n\\n"
                                f"📊 총 {self.total_trades}회 | 승률 {(self.winning_trades/self.total_trades*100) if self.total_trades > 0 else 0:.1f}% | {self.total_pnl:+,.0f}원"
                            )

                # 포지션이 있으면 매도 체크
                if self.position:
                    ticker = self.upbit.get_current_price(self.market)
                    current_price = ticker['trade_price']

                    sell_signal = self.check_sell_signal(current_price)

                    if sell_signal:
                        self.execute_sell(sell_signal)
                    else:
                        profit_pct = ((current_price - self.position['buy_price']) / self.position['buy_price']) * 100
                        hold_minutes = (datetime.now() - self.position['buy_time']).total_seconds() / 60
                        self.log(f"[BTC] {profit_pct:+.2f}% (피크: {self.position_peak:+.2f}%) | {hold_minutes:.0f}분")

                # 포지션 없으면 매수 신호 체크
                else:
                    buy_signal = self.check_buy_signal()
                    if buy_signal:
                        self.execute_buy(buy_signal)
                    else:
                        self.log("⏸️  매수 신호 없음 (대기)")

                time.sleep(check_interval)

            except KeyboardInterrupt:
                self.log("\n봇 종료")
                break
            except Exception as e:
                self.log(f"❌ 오류: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(check_interval)


if __name__ == "__main__":
    try:
        config = get_config()

        print("=" * 60)
        print("₿ 비트코인 전용 보수적 트레이딩 봇")
        print("=" * 60)

        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = SimpleTelegramBot(config['telegram_token'], config['telegram_chat_id'])

        telegram.send_message(
            "₿ <b>비트코인 전용 봇 시작</b>\\n"
            "━━━━━━━━━━━━━━━━━\\n\\n"
            "💰 대장 코인만 거래 (안정성 우선)\\n"
            "📊 매수: RSI 과매도 + BB하단\\n"
            "🎯 목표: 1.0% / 1.5%\\n"
            "🛑 손절: -0.6%\\n"
            "⏱️  최대: 180분\\n"
            "🔄 체크: 2분마다"
        )

        bot = BitcoinOnlyBot(upbit, telegram)
        bot.run(check_interval=120)

    except KeyboardInterrupt:
        print("\n봇 종료됨")
    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
