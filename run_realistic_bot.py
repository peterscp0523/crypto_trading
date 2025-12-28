"""
현실적인 초단타 봇
- 목표: 0.25% (수수료 5배)
- 손절: -0.15% (타이트)
- 포지션: 1개만 (집중)
- 시간: 2-10분 (빠른 회전)
"""
import os
import time
from datetime import datetime
from telegram_bot import TelegramBot
from upbit_api import UpbitAPI
from config import get_config
from realistic_strategy import RealisticScalpingStrategy, SingleCoinFocusSelector


class RealisticTradingBot:
    """현실적인 초단타 봇"""

    def __init__(self, upbit, telegram):
        self.upbit = upbit
        self.telegram = telegram

        self.strategy = RealisticScalpingStrategy()
        self.coin_selector = SingleCoinFocusSelector(upbit)

        self.position = None  # 현재 포지션 (1개만)
        self.target_market = None  # 타겟 코인
        self.last_coin_selection = None  # 마지막 코인 선택 시각

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
        coin_balance = {}

        for acc in accounts:
            currency = acc['currency']
            balance = float(acc['balance'])
            avg_buy_price = float(acc['avg_buy_price'])

            if currency == 'KRW':
                krw = balance
            elif balance > 0:
                coin_balance[currency] = {
                    'balance': balance,
                    'avg_price': avg_buy_price
                }

        return krw, coin_balance

    def select_target_coin(self):
        """타겟 코인 선택 (10분마다)"""
        now = datetime.now()

        if not self.last_coin_selection or \
           (now - self.last_coin_selection).total_seconds() > 600:

            self.log("🔄 타겟 코인 재선택...")
            self.target_market = self.coin_selector.get_best_single_coin()
            self.last_coin_selection = now

            if self.target_market:
                self.telegram.send_message(
                    f"🎯 <b>타겟 코인 변경</b>\n"
                    f"━━━━━━━━━━━━━━━━━\n\n"
                    f"새 타겟: {self.target_market}"
                )

    def check_and_trade(self):
        """매매 체크"""
        try:
            # 1. 타겟 코인 선택
            self.select_target_coin()

            if not self.target_market:
                self.log("⚠️ 타겟 코인 없음")
                return

            # 2. 현재가 조회
            ticker = self.upbit.get_current_price(self.target_market)
            current_price = ticker['trade_price']

            # 3. 포지션 있으면 매도 체크
            if self.position:
                sell_signal = self.strategy.check_sell_signal(self.position, current_price)

                if sell_signal:
                    self.execute_sell(sell_signal, current_price)
                else:
                    # 포지션 상태 출력
                    buy_price = self.position['buy_price']
                    profit_pct = ((current_price - buy_price) / buy_price) * 100
                    hold_seconds = (datetime.now() - self.position['buy_time']).total_seconds()

                    self.log(f"[{self.target_market}] 포지션: {profit_pct:+.2f}% | {int(hold_seconds)}초 보유")

            # 4. 포지션 없으면 매수 체크
            else:
                candles = self.upbit.get_candles(self.target_market, "minutes", 1, 10)

                if not candles:
                    return

                buy_signal = self.strategy.check_buy_signal(candles)

                if buy_signal:
                    self.execute_buy(buy_signal, current_price)

        except Exception as e:
            self.log(f"❌ 체크 실패: {e}")
            import traceback
            traceback.print_exc()

    def execute_buy(self, signal, current_price):
        """매수 실행"""
        try:
            krw, coin_balance = self.get_balance()

            # 90% 투자 (10% 버퍼)
            invest_krw = int(krw * 0.9)

            if invest_krw < 5000:
                self.log(f"⏸️ 매수 스킵: 잔고 부족 ({krw:,.0f}원)")
                return

            self.log(f"💰 매수 시도: {self.target_market}")
            self.log(f"  금액: {invest_krw:,.0f}원 @ {current_price:,.0f}원")
            self.log(f"  사유: {signal['reason']}")

            # 주문 실행
            result = self.upbit.order_market_buy(self.target_market, invest_krw)

            if result and 'uuid' in result:
                uuid = result['uuid']

                # 체결 대기
                time.sleep(0.5)

                # 실제 체결 정보 조회
                order_info = self.upbit.get_order(uuid)

                if order_info and float(order_info.get('executed_volume', 0)) > 0:
                    # 체결가 추출
                    trades = order_info.get('trades', [])
                    if trades:
                        total_funds = sum(float(t['funds']) for t in trades)
                        total_volume = sum(float(t['volume']) for t in trades)
                        executed_price = total_funds / total_volume
                        amount = total_volume
                    else:
                        executed_price = float(order_info.get('avg_price', current_price))
                        amount = float(order_info.get('executed_volume', 0))

                    # 포지션 등록
                    self.position = {
                        'market': self.target_market,
                        'buy_price': executed_price,
                        'buy_time': datetime.now(),
                        'amount': amount,
                        'target_profit': signal['target_profit'],
                        'stop_loss': signal['stop_loss']
                    }

                    self.log(f"✅ 매수 완료: {amount:.8f}개 @ {executed_price:,.0f}원")

                    self.telegram.send_message(
                        f"💰 <b>매수 완료</b>\n"
                        f"━━━━━━━━━━━━━━━━━\n\n"
                        f"코인: {self.target_market}\n"
                        f"수량: {amount:.8f}\n"
                        f"가격: {executed_price:,.0f}원\n"
                        f"금액: {invest_krw:,.0f}원\n\n"
                        f"사유: {signal['reason']}\n"
                        f"목표: +{signal['target_profit']*100:.2f}%\n"
                        f"손절: {signal['stop_loss']*100:.2f}%"
                    )
                else:
                    self.log(f"❌ 체결 실패: {result}")
            else:
                error_msg = result.get('error', {}).get('message', '알 수 없는 오류') if result else '응답 없음'
                self.log(f"❌ 주문 실패: {error_msg}")

        except Exception as e:
            self.log(f"❌ 매수 실패: {e}")
            import traceback
            traceback.print_exc()

    def execute_sell(self, signal, current_price):
        """매도 실행"""
        try:
            amount = self.position['amount']
            buy_price = self.position['buy_price']
            market = self.position['market']

            profit_krw = (current_price - buy_price) * amount
            profit_pct = ((current_price - buy_price) / buy_price) * 100

            self.log(f"💸 매도 시도: {market}")
            self.log(f"  수량: {amount:.8f}개 @ {current_price:,.0f}원")
            self.log(f"  사유: {signal['reason']}")

            # 주문 실행
            result = self.upbit.order_market_sell(market, amount)

            if result and 'uuid' in result:
                self.log(f"✅ 매도 완료: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)")

                # 통계 업데이트
                self.total_trades += 1
                self.total_pnl += profit_krw
                if profit_krw > 0:
                    self.winning_trades += 1

                win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

                self.telegram.send_message(
                    f"💸 <b>매도 완료</b>\n"
                    f"━━━━━━━━━━━━━━━━━\n\n"
                    f"코인: {market}\n"
                    f"수량: {amount:.8f}\n"
                    f"손익: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)\n\n"
                    f"사유: {signal['reason']}\n\n"
                    f"📊 <b>누적 통계</b>\n"
                    f"총 거래: {self.total_trades}회\n"
                    f"승률: {win_rate:.1f}%\n"
                    f"총 손익: {self.total_pnl:+,.0f}원"
                )

                # 포지션 해제
                self.position = None
            else:
                error_msg = result.get('error', {}).get('message', '알 수 없는 오류') if result else '응답 없음'
                self.log(f"❌ 매도 실패: {error_msg}")

        except Exception as e:
            self.log(f"❌ 매도 실패: {e}")
            import traceback
            traceback.print_exc()

    def run(self, check_interval=10):
        """봇 실행"""
        self.log("=" * 70)
        self.log("🚀 현실적인 초단타 봇 시작")
        self.log("=" * 70)
        self.log(f"목표 수익: +{self.strategy.target_profit*100:.2f}%")
        self.log(f"손절: {self.strategy.stop_loss*100:.2f}%")
        self.log(f"체크 간격: {check_interval}초")
        self.log("=" * 70)

        self.telegram.send_message(
            f"🚀 <b>초단타 봇 시작</b>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📊 전략: 현실적 초단타\n"
            f"🎯 목표: +{self.strategy.target_profit*100:.2f}%\n"
            f"🛑 손절: {self.strategy.stop_loss*100:.2f}%\n"
            f"⏱️ 시간: 2-10분\n"
            f"💼 포지션: 1개 집중"
        )

        while True:
            try:
                self.check_and_trade()
                time.sleep(check_interval)

            except KeyboardInterrupt:
                self.log("\n봇 종료")
                break
            except Exception as e:
                self.log(f"❌ 오류: {e}")
                time.sleep(check_interval)


if __name__ == "__main__":
    try:
        config = get_config()

        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

        bot = RealisticTradingBot(upbit, telegram)
        bot.run(check_interval=10)  # 10초마다 체크

    except KeyboardInterrupt:
        print("\n봇 종료")
    except Exception as e:
        print(f"❌ 시작 실패: {e}")
        import traceback
        traceback.print_exc()
