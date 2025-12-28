"""
단일 코인 집중 전략 봇 (동적 스캔)
10개 코인 실시간 스캔 → 최고 기회에 90% 집중 투자
"""
import os
import time
from upbit_api import UpbitAPI
from database_manager import DatabaseManager
from dynamic_coin_scanner import DynamicCoinScanner
from volatility_strategy import VolatilityScalpingStrategy
from ma_crossover_strategy import MACrossoverStrategy
from bear_market_strategy import BearMarketStrategy
from config import get_config


class SimpleTelegramBot:
    """간단한 텔레그램 봇"""

    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

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


class SingleCoinBot:
    """단일 코인 집중 봇"""

    def __init__(self, upbit, telegram, db=None):
        self.upbit = upbit
        self.telegram = telegram
        self.db = db

        # 동적 스캐너
        self.scanner = DynamicCoinScanner(upbit)

        # 전략들
        self.strategies = {
            'scalping': VolatilityScalpingStrategy(),
            'ma': MACrossoverStrategy(),
            'bear': BearMarketStrategy()
        }

        # 포지션
        self.position = None
        self.position_peak = 0

        # 통계
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0

    def log(self, msg):
        """로그 출력"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    def get_balance(self):
        """잔고 조회"""
        accounts = self.upbit.get_accounts()
        krw = 0
        holdings = {}

        for acc in accounts:
            currency = acc['currency']
            balance = float(acc['balance'])

            if currency == 'KRW':
                krw = balance
            elif balance > 0:
                holdings[currency] = {
                    'balance': balance,
                    'avg_price': float(acc['avg_buy_price'])
                }

        return krw, holdings

    def check_sell_signal(self, market, current_price):
        """매도 신호 체크"""
        if not self.position:
            return None

        from datetime import datetime

        buy_price = self.position['buy_price']
        buy_time = self.position['buy_time']
        strategy = self.position.get('strategy', 'scalping')

        profit_pct = ((current_price - buy_price) / buy_price) * 100
        hold_minutes = (datetime.now() - buy_time).total_seconds() / 60

        # 피크 추적
        if profit_pct > self.position_peak:
            self.position_peak = profit_pct

        # 1. 목표 수익 달성 (0.8%)
        if profit_pct >= 0.8:
            return {
                'reason': f'목표 달성 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 2. 빠른 익절 (0.5%, 10분 내)
        if hold_minutes < 10 and profit_pct >= 0.5:
            return {
                'reason': f'빠른 익절 ({hold_minutes:.0f}분, {profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 3. 기본 익절 (0.35%)
        if profit_pct >= 0.35:
            return {
                'reason': f'익절 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 4. 트레일링 스톱 (피크에서 -0.4% 하락) - 익절 우선
        if self.position_peak > 0.5 and (self.position_peak - profit_pct) > 0.4:
            return {
                'reason': f'트레일링 스톱 (피크 {self.position_peak:.2f}% → {profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 5. 시간 초과 강제 청산 (60분)
        if hold_minutes > 60:
            return {
                'reason': f'시간 초과 ({hold_minutes:.0f}분, {profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        # 6. 극단적 손절 (-0.8%) - 최후의 수단만
        if profit_pct <= -0.8:
            return {
                'reason': f'극한 손절 ({profit_pct:.2f}%)',
                'profit_pct': profit_pct
            }

        return None

    def execute_buy(self, opportunity):
        """매수 실행"""
        try:
            market = opportunity['market']
            signal = opportunity['signal']
            strategy = opportunity['strategy']

            krw, holdings = self.get_balance()

            # 90% 투자
            invest_krw = int(krw * 0.9)

            if invest_krw < 5000:
                self.log(f"⏸️ 잔고 부족: {krw:,.0f}원")
                return False

            self.log(f"💰 매수 시도: {market} ({strategy})")
            self.log(f"   금액: {invest_krw:,.0f}원")
            self.log(f"   사유: {signal['reason']}")

            # 주문
            result = self.upbit.order_market_buy(market, invest_krw)

            if result and 'uuid' in result:
                uuid = result['uuid']
                time.sleep(0.5)

                # 체결 정보 조회
                order_info = self.upbit.get_order(uuid)

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

                    # 포지션 등록
                    from datetime import datetime
                    self.position = {
                        'market': market,
                        'buy_price': executed_price,
                        'buy_time': datetime.now(),
                        'amount': amount,
                        'strategy': strategy
                    }
                    self.position_peak = 0

                    self.log(f"✅ 매수 완료: {amount:.8f}개 @ {executed_price:,.0f}원")

                    self.telegram.send_message(
                        f"💰 <b>매수 완료</b>\\n"
                        f"━━━━━━━━━━━━━━━━━\\n\\n"
                        f"코인: {market}\\n"
                        f"전략: {strategy}\\n"
                        f"수량: {amount:.8f}\\n"
                        f"가격: {executed_price:,.0f}원\\n"
                        f"금액: {invest_krw:,.0f}원\\n\\n"
                        f"사유: {signal['reason']}\\n\\n"
                        f"🎯 익절: +0.35% / +0.5% / +0.8%\\n"
                        f"🛑 손절: -0.8% (극단적 상황)\\n"
                        f"⏱️  최대: 60분"
                    )

                    return True
                else:
                    self.log(f"❌ 체결 실패")
                    return False
            else:
                error = result.get('error', {}).get('message', '알 수 없음') if result else '응답 없음'
                self.log(f"❌ 주문 실패: {error}")
                return False

        except Exception as e:
            self.log(f"❌ 매수 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def execute_sell(self, sell_signal):
        """매도 실행"""
        try:
            market = self.position['market']
            amount = self.position['amount']
            buy_price = self.position['buy_price']
            profit_pct = sell_signal['profit_pct']
            reason = sell_signal['reason']

            self.log(f"💸 매도 시도: {market}")
            self.log(f"   사유: {reason}")

            result = self.upbit.order_market_sell(market, amount)

            if result and 'uuid' in result:
                profit_krw = (amount * buy_price) * (profit_pct / 100)

                # 통계 업데이트
                self.total_trades += 1
                self.total_pnl += profit_krw
                if profit_krw > 0:
                    self.winning_trades += 1

                win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

                self.log(f"✅ 매도 완료: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)")

                self.telegram.send_message(
                    f"💸 <b>매도 완료</b>\\n"
                    f"━━━━━━━━━━━━━━━━━\\n\\n"
                    f"코인: {market}\\n"
                    f"수량: {amount:.8f}\\n"
                    f"손익: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)\\n\\n"
                    f"사유: {reason}\\n\\n"
                    f"📊 <b>누적 통계</b>\\n"
                    f"총 거래: {self.total_trades}회\\n"
                    f"승률: {win_rate:.1f}%\\n"
                    f"총 손익: {self.total_pnl:+,.0f}원"
                )

                # 포지션 해제
                self.position = None
                self.position_peak = 0

                return True
            else:
                error = result.get('error', {}).get('message', '알 수 없음') if result else '응답 없음'
                self.log(f"❌ 매도 실패: {error}")
                return False

        except Exception as e:
            self.log(f"❌ 매도 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self, check_interval=30):
        """봇 실행"""
        self.log("=" * 70)
        self.log("🎯 단일 코인 집중 봇 시작 (동적 스캔)")
        self.log("=" * 70)
        self.log(f"📊 스캔 대상: 10개 코인 (10분마다 갱신)")
        self.log(f"💰 포지션: 1개 90% 집중")
        self.log(f"🎯 익절 우선: 0.35% / 0.5% / 0.8%")
        self.log(f"🛑 손절: -0.8% (극단적 상황만)")
        self.log(f"⏱️  보유 시간: 최대 60분")
        self.log(f"⏱️  체크: {check_interval}초마다")
        self.log("=" * 70)

        while True:
            try:
                # 포지션 있으면 매도 체크
                if self.position:
                    market = self.position['market']
                    ticker = self.upbit.get_current_price(market)
                    current_price = ticker['trade_price']

                    sell_signal = self.check_sell_signal(market, current_price)

                    if sell_signal:
                        self.execute_sell(sell_signal)
                    else:
                        buy_price = self.position['buy_price']
                        profit_pct = ((current_price - buy_price) / buy_price) * 100
                        from datetime import datetime
                        hold_minutes = (datetime.now() - self.position['buy_time']).total_seconds() / 60
                        self.log(f"[{market}] {profit_pct:+.2f}% (피크: {self.position_peak:+.2f}%) | {hold_minutes:.0f}분")

                # 포지션 없으면 매수 기회 스캔
                else:
                    opportunity = self.scanner.scan_all_opportunities(self.strategies)

                    if opportunity:
                        self.execute_buy(opportunity)

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
        print("🎯 단일 코인 집중 전략 봇 시작 (동적 스캔)")
        print("=" * 60)

        # 데이터베이스 (선택적)
        use_oracle = os.environ.get('USE_ORACLE_DB', 'false').lower() == 'true'
        db = None
        if use_oracle or os.environ.get('USE_DB', 'false').lower() == 'true':
            try:
                db = DatabaseManager(use_oracle=use_oracle)
                print(f"✅ 데이터베이스: {'Oracle Cloud' if use_oracle else 'SQLite'}")
            except Exception as e:
                print(f"⚠️ DB 연동 실패: {e}")
                db = None

        # API 초기화
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = SimpleTelegramBot(config['telegram_token'], config['telegram_chat_id'])

        # 시작 메시지
        telegram.send_message(
            "🎯 <b>단일 코인 집중 봇 시작 (익절 우선)</b>\\n"
            "━━━━━━━━━━━━━━━━━\\n\\n"
            "📊 10개 코인 실시간 스캔\\n"
            "💰 최고 기회에 90% 집중\\n\\n"
            "🎯 익절: 0.35% / 0.5% / 0.8%\\n"
            "🛑 손절: -0.8% (극단적 상황만)\\n"
            "⏱️  최대 보유: 60분\\n"
            "🔄 체크: 30초마다"
        )

        # 봇 실행
        bot = SingleCoinBot(upbit, telegram, db)
        bot.run(check_interval=30)

    except KeyboardInterrupt:
        print("\n봇 종료됨")
    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
