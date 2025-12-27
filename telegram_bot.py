import os
import time
import requests
from datetime import datetime, timedelta
from upbit_api import UpbitAPI
from trading_indicators import TechnicalIndicators
from advanced_strategy import AdvancedIndicators
from market_scanner import MarketScanner
from advanced_features import VolatilityManager, TimeBasedStrategy, AdvancedRiskManager
from database_manager import DatabaseManager
from concurrent.futures import ThreadPoolExecutor



class TelegramBot:
    """텔레그램 봇"""
    
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, text):
        """메시지 전송"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            response = requests.post(url, data=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"텔레그램 전송 실패: {e}")
            return None
    
    def get_updates(self, offset=None):
        """메시지 가져오기"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"timeout": 1, "offset": offset}
            response = requests.get(url, params=params, timeout=5)
            return response.json()
        except Exception as e:
            return None


class TradingBot:
    """자동매매 봇"""
    
    def __init__(self, upbit, telegram, market="KRW-ETH", dry_run=False, signal_timeframe=15,
                 enable_multi_coin=False, db=None):
        self.upbit = upbit
        self.telegram = telegram
        self.market = market
        self.dry_run = dry_run  # 시뮬레이션 모드
        self.signal_timeframe = signal_timeframe  # 신호 타임프레임 (5, 15, 60분)
        self.enable_multi_coin = enable_multi_coin  # 멀티 코인 모드
        self.db = db  # 데이터베이스 매니저 (선택적)

        # 전략 파라미터 (다층 익절 시스템)
        self.rsi_buy = 35            # 30 → 35 (더 많은 기회)
        self.rsi_sell = 70           # 70 유지

        # 다층 익절 전략 (빠른 수익 실현) - 기본값
        self.quick_profit = 0.008    # 0.8% 퀵 익절 (30분 이내)
        self.take_profit_1 = 0.015   # 1.5% 1차 익절
        self.take_profit_2 = 0.025   # 2.5% 2차 익절
        self.take_profit_3 = 0.04    # 4.0% 최종 익절

        self.stop_loss = -0.015      # -2% → -1.5% (더 빠른 손절)

        # 동적 트레일링 스톱
        self.trailing_stop_tight = 0.003   # 0.3% 수익 이후 -0.3% 트레일링
        self.trailing_stop_medium = 0.005  # 0.8% 수익 이후 -0.5% 트레일링
        self.trailing_stop_wide = 0.008    # 1.5% 수익 이후 -0.8% 트레일링

        # 포지션 타임아웃
        self.position_timeout_hours = 3    # 3시간 이후 강제 청산 검토

        self.bb_period = 20
        self.bb_std = 2
        self.volume_threshold = 1.2  # 1.3 → 1.2 (더욱 완화)

        # DB에서 최적 파라미터 로드
        self.load_optimized_parameters()

        # 멀티 코인 설정
        self.market_scanner = MarketScanner(upbit) if enable_multi_coin else None
        self.coin_switch_score_diff = 20  # 코인 전환 최소 점수 차이
        self.last_coin_scan = None

        # 상태
        self.position = None
        self.trade_history = []
        self.is_running = True
        self.error_count = 0
        self.last_daily_report = None
        self.position_peak_profit = 0
        self.position_lowest_profit = 0
        self.last_update_id = None
        self.executor = ThreadPoolExecutor(max_workers=3)

        # 드라이런 모드용 가상 잔고
        if self.dry_run:
            self.virtual_krw = 1000000  # 100만원
            self.virtual_coin = 0
            self.virtual_avg_price = 0

    def load_optimized_parameters(self):
        """데이터베이스에서 최적화된 파라미터 로드"""
        if not self.db:
            return

        try:
            params = self.db.get_active_parameters(self.market)

            if params:
                self.quick_profit = params['quick_profit']
                self.take_profit_1 = params['take_profit_1']
                self.take_profit_2 = params.get('take_profit_2', 0.025)
                self.stop_loss = params['stop_loss']
                self.trailing_stop_tight = params['trailing_stop_tight']
                self.trailing_stop_medium = params.get('trailing_stop_medium', 0.005)
                self.trailing_stop_wide = params.get('trailing_stop_wide', 0.008)

                print(f"✅ DB에서 최적 파라미터 로드 완료 ({self.market})")
                print(f"   최적화 일자: {params['last_optimized']}")
                print(f"   퀵익절: {self.quick_profit*100:.1f}%")
                print(f"   1차익절: {self.take_profit_1*100:.1f}%")
                print(f"   손절: {self.stop_loss*100:.1f}%")
            else:
                print(f"ℹ️  {self.market} 최적화 데이터 없음, 기본 파라미터 사용")

        except Exception as e:
            print(f"⚠️ 파라미터 로드 실패, 기본값 사용: {e}")

    def save_trade_to_db(self, trade_data):
        """거래 기록을 데이터베이스에 저장"""
        if not self.db:
            return

        try:
            self.db.save_trade(trade_data)
            print(f"✅ 거래 기록 DB 저장 완료")
        except Exception as e:
            print(f"⚠️ 거래 기록 저장 실패: {e}")

    def get_current_status(self):
        """현재 계좌 및 시장 상태"""
        # 드라이런 모드
        if self.dry_run:
            ticker = self.upbit.get_current_price(self.market)
            current_price = ticker['trade_price']
            change_24h = ticker.get('signed_change_rate', 0) * 100

            return {
                'krw': self.virtual_krw,
                'coin': self.virtual_coin,
                'avg_price': self.virtual_avg_price,
                'current_price': current_price,
                'coin_value': self.virtual_coin * current_price,
                'total': self.virtual_krw + (self.virtual_coin * current_price),
                'change_24h': change_24h
            }

        # 실제 모드
        accounts = self.upbit.get_accounts()

        krw = 0
        coin = 0
        avg_price = 0

        for acc in accounts:
            if acc['currency'] == 'KRW':
                krw = float(acc['balance'])
            elif acc['currency'] == self.market.split('-')[1]:
                coin = float(acc['balance'])
                avg_price = float(acc['avg_buy_price'])

        ticker = self.upbit.get_current_price(self.market)
        current_price = ticker['trade_price']
        change_24h = ticker.get('signed_change_rate', 0) * 100

        return {
            'krw': krw,
            'coin': coin,
            'avg_price': avg_price,
            'current_price': current_price,
            'coin_value': coin * current_price,
            'total': krw + (coin * current_price),
            'change_24h': change_24h
        }

    def get_trend_analysis(self):
        """다중 시간대 추세 분석 (1H + 4H)"""
        try:
            # 1시간봉 200개 (약 8일치)
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 200)
            # 4시간봉 200개 (약 33일치)
            candles_4h = self.upbit.get_candles(self.market, "minutes", 240, 200)

            if len(candles_1h) < 50 or len(candles_4h) < 50:
                return None

            # 1시간 추세
            prices_1h = [c['trade_price'] for c in candles_1h]
            rsi_1h = TechnicalIndicators.calculate_rsi(prices_1h, 14)
            ma20_1h = sum(prices_1h[:20]) / 20
            ma50_1h = sum(prices_1h[:50]) / 50
            trend_1h = "up" if ma20_1h > ma50_1h and prices_1h[0] > ma20_1h else "down"

            # 4시간 추세
            prices_4h = [c['trade_price'] for c in candles_4h]
            rsi_4h = TechnicalIndicators.calculate_rsi(prices_4h, 14)
            ma20_4h = sum(prices_4h[:20]) / 20
            ma50_4h = sum(prices_4h[:50]) / 50
            trend_4h = "up" if ma20_4h > ma50_4h and prices_4h[0] > ma20_4h else "down"

            # 추세 상태 판단 (RSI 기준 완화)
            if trend_1h == "up" and trend_4h == "up":
                trend_state = "strong_bull"  # 강한 상승
                buy_allowed = True
                rsi_threshold = 50  # 40 → 50
            elif trend_1h == "down" and trend_4h == "up":
                trend_state = "correction"   # 조정 (상승장 내 조정)
                buy_allowed = True
                rsi_threshold = 45  # 35 → 45
            elif trend_1h == "up" and trend_4h == "down":
                trend_state = "weak_bounce"  # 약한 반등
                buy_allowed = True
                rsi_threshold = 40  # 30 → 40
            else:  # trend_1h == "down" and trend_4h == "down"
                trend_state = "strong_bear"  # 강한 하락
                buy_allowed = True  # False → True (하락장에서도 매수)
                rsi_threshold = 30  # 25 → 30

            return {
                'trend_1h': trend_1h,
                'trend_4h': trend_4h,
                'rsi_1h': rsi_1h,
                'rsi_4h': rsi_4h,
                'trend_state': trend_state,
                'buy_allowed': buy_allowed,
                'rsi_threshold': rsi_threshold,
                'ma20_1h': ma20_1h,
                'ma50_1h': ma50_1h,
                'ma20_4h': ma20_4h,
                'ma50_4h': ma50_4h
            }

        except Exception as e:
            self.log(f"추세 분석 실패: {e}")
            return None
    
    def get_signals(self, timeframe=15):
        """시장 분석 및 신호 (다중 시간대 포함)

        Args:
            timeframe: 5, 15, 60 등 (분 단위)
        """
        candles = self.upbit.get_candles(self.market, "minutes", timeframe, 50)
        if len(candles) < 50:
            return None

        prices = [c['trade_price'] for c in candles]
        volumes = [c['candle_acc_trade_volume'] for c in candles]

        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        upper, middle, lower = AdvancedIndicators.calculate_bollinger_bands(prices, 20, 2)
        vol_ma = AdvancedIndicators.calculate_volume_ma(volumes, 20)

        if not all([rsi, upper, lower, vol_ma]):
            return None

        current_price = prices[0]
        current_vol = volumes[0]
        bb_pos = ((current_price - lower) / (upper - lower)) * 100

        # 다중 시간대 추세 분석
        trend = self.get_trend_analysis()

        # 매수 조건 (완화됨 - 거래량 조건 제거/완화)
        buy_signal = False
        if trend and trend['buy_allowed']:
            rsi_threshold = trend['rsi_threshold']

            # 추세별 조건
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
            'bb_pos': bb_pos,
            'vol_ratio': current_vol / vol_ma,
            'trend': trend,
            'buy': buy_signal,
            'sell': rsi > self.rsi_sell and current_price >= upper * 0.99
        }
    
    def buy(self, status, signals):
        """매수 실행 (고급 기능 통합)"""
        krw = status['krw']
        if krw < 5000:
            return False

        try:
            price = signals['price']

            # === 시간대별 전략 체크 ===
            session = TimeBasedStrategy.get_trading_session()
            self.log(f"⏰ {session['name']} (공격성: {session['aggression']}, 변동성: {session['volatility']})")

            # === 변동성 기반 포지션 사이징 ===
            # 1시간봉으로 ATR 계산
            candles_1h = self.upbit.get_candles(self.market, "minutes", 60, 30)
            atr = VolatilityManager.calculate_atr(candles_1h, 14) if candles_1h else None

            # 포지션 크기 결정
            position_krw = VolatilityManager.get_position_size(krw, price, atr)

            # 거래 기록 기반 포지션 비율 조정
            if len(self.trade_history) >= 10:
                optimal_ratio = AdvancedRiskManager.get_optimal_position_ratio(self.trade_history)
                position_krw = int(krw * optimal_ratio)

            # 최소 금액 체크
            if position_krw < 5000:
                position_krw = min(krw, 5000)

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                amount = position_krw / price
                self.virtual_coin = amount
                self.virtual_krw = krw - position_krw
                self.virtual_avg_price = price
            # 실제 주문
            else:
                result = self.upbit.order_market_buy(self.market, position_krw)

            amount = position_krw / price
            
            self.position = {
                'buy_price': price,
                'buy_time': datetime.now(),
                'amount': amount,
                'buy_krw': krw
            }
            
            self.position_peak_profit = 0
            self.position_lowest_profit = 0
            
            self.trade_history.append({
                'type': 'BUY',
                'time': datetime.now(),
                'price': price,
                'amount': krw
            })
            
            trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
            trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}🔵 <b>매수 완료</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"⏰ {session['name']} (공격성: {session['aggression']})\n"
            msg += f"💰 금액: {position_krw:,.0f}원 / {krw:,.0f}원 ({position_krw/krw*100:.0f}%)\n"
            msg += f"📊 가격: {price:,.0f}원\n"
            msg += f"🪙 수량: {amount:.6f} {self.market.split('-')[1]}\n\n"

            if signals.get('trend'):
                trend = signals['trend']
                state = trend['trend_state']
                msg += f"📈 추세: {trend_emoji.get(state, '📊')} {trend_name.get(state, state)}\n"
                msg += f"  • 1H: {'↑' if trend['trend_1h'] == 'up' else '↓'} RSI {trend['rsi_1h']:.1f}\n"
                msg += f"  • 4H: {'↑' if trend['trend_4h'] == 'up' else '↓'} RSI {trend['rsi_4h']:.1f}\n\n"

            msg += f"📊 지표:\n"
            msg += f"  • RSI: {signals['rsi']:.1f}\n"
            msg += f"  • 볼린저: {signals['bb_pos']:.1f}%\n"
            msg += f"  • 거래량: {signals['vol_ratio']:.2f}x\n\n"
            msg += f"🎯 익절 목표 (다층):\n"
            msg += f"  • ⚡ 퀵: {price * (1 + self.quick_profit):,.0f}원 (+{self.quick_profit*100:.1f}%, 30분내)\n"
            msg += f"  • 1차: {price * (1 + self.take_profit_1):,.0f}원 (+{self.take_profit_1*100:.1f}%)\n"
            msg += f"  • 2차: {price * (1 + self.take_profit_2):,.0f}원 (+{self.take_profit_2*100:.1f}%)\n"
            msg += f"  • 최종: {price * (1 + self.take_profit_3):,.0f}원 (+{self.take_profit_3*100:.0f}%)\n\n"
            msg += f"🛡️ 리스크 관리:\n"
            msg += f"  • 손절: {price * (1 + self.stop_loss):,.0f}원 ({self.stop_loss*100:.1f}%)\n"
            msg += f"  • 트레일링: 0.3%↑시 -0.3%, 0.8%↑시 -0.5%, 1.5%↑시 -0.8%\n"
            msg += f"  • 타임아웃: {self.position_timeout_hours}시간\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self.telegram.send_message(msg)
            self.log("✅ 매수 완료")
            return True
            
        except Exception as e:
            self.log(f"❌ 매수 실패: {e}")
            self.telegram.send_message(f"❌ 매수 실패: {e}")
            return False
    
    def sell(self, status, signals, reason):
        """매도 실행"""
        if not self.position:
            return False
        
        coin = status['coin']
        if coin < 0.001:
            self.position = None
            return False
        
        try:
            price = signals['price']
            buy_price = self.position['buy_price']
            profit_rate = (price - buy_price) / buy_price * 100
            
            hold_hours = (datetime.now() - self.position['buy_time']).total_seconds() / 3600

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                sell_krw = coin * price
                profit = sell_krw - self.position['buy_krw']
                self.virtual_krw = sell_krw
                self.virtual_coin = 0
                self.virtual_avg_price = 0
            # 실제 주문
            else:
                self.upbit.order_market_sell(self.market, coin)

            sell_krw = coin * price
            profit = sell_krw - self.position['buy_krw']

            # 거래 기록 생성
            trade_record = {
                'market': self.market,
                'type': 'SELL',
                'time': datetime.now(),
                'price': price,
                'amount': coin,
                'krw_amount': sell_krw,
                'profit': profit,
                'profit_rate': profit_rate / 100,  # DB에는 0.01 형식으로 저장
                'reason': reason,
                'hold_time_minutes': int(hold_hours * 60),
                'peak_profit': self.position_peak_profit
            }

            self.trade_history.append(trade_record)

            # 데이터베이스에 저장
            self.save_trade_to_db(trade_record)

            emoji = "🟢" if profit > 0 else "🔴"
            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}{emoji} <b>매도 완료</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 금액: {sell_krw:,.0f}원\n"
            msg += f"📊 가격: {price:,.0f}원\n"
            msg += f"📈 매수가: {buy_price:,.0f}원\n\n"
            msg += f"💵 <b>수익: {profit:+,.0f}원 ({profit_rate:+.2f}%)</b>\n\n"
            msg += f"📊 통계:\n"
            msg += f"  • 보유: {hold_hours:.1f}시간\n"
            msg += f"  • 최고: {self.position_peak_profit*100:+.2f}%\n"
            msg += f"  • 최저: {self.position_lowest_profit*100:+.2f}%\n\n"
            msg += f"📝 사유: {reason}\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self.telegram.send_message(msg)
            self.log("✅ 매도 완료")
            
            self.position = None
            self.position_peak_profit = 0
            self.position_lowest_profit = 0
            
            return True
            
        except Exception as e:
            self.log(f"❌ 매도 실패: {e}")
            self.telegram.send_message(f"❌ 매도 실패: {e}")
            return False
    
    def check_multi_coin_switch(self):
        """멀티 코인 모드: 더 나은 코인으로 전환 검토"""
        if not self.enable_multi_coin or not self.market_scanner:
            return False

        # 포지션 없을 때만 코인 변경 고려
        if self.position:
            return False

        # 10분마다 스캔 (API 부하 줄이기)
        now = datetime.now()
        if self.last_coin_scan and (now - self.last_coin_scan).total_seconds() < 600:
            return False

        self.last_coin_scan = now

        try:
            # 현재 모멘텀 랭킹 확인
            best_coin = self.market_scanner.get_best_coin()

            if not best_coin:
                return False

            # 현재 코인과 다르고, 점수 차이가 크면 전환
            if best_coin['market'] != self.market:
                self.log(f"💱 코인 전환: {self.market} → {best_coin['market']} "
                        f"(점수: {best_coin['score']})")

                # 텔레그램 알림
                msg = f"💱 <b>코인 전환</b>\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"기존: {self.market.replace('KRW-', '')}\n"
                msg += f"신규: {best_coin['name']}\n\n"
                msg += f"📊 모멘텀 점수: {best_coin['score']}\n"
                msg += f"📈 24H 변화: {best_coin['change_24h']:+.2f}%\n"
                msg += f"💰 거래액: {best_coin['volume_24h']/100_000_000:,.0f}억원"
                self.telegram.send_message(msg)

                # 마켓 변경
                self.market = best_coin['market']
                return True

            return False

        except Exception as e:
            self.log(f"코인 전환 검토 실패: {e}")
            return False

    def check_and_trade(self):
        """메인 로직"""
        try:
            # 멀티 코인 모드: 코인 전환 검토
            self.check_multi_coin_switch()

            status = self.get_current_status()
            signals = self.get_signals(self.signal_timeframe)

            if not signals:
                self.log("신호 없음")
                return

            self.log(f"\n[{datetime.now().strftime('%H:%M:%S')}] 체크 ({self.market.replace('KRW-', '')})")
            self.log(f"자산: {status['total']:,.0f}원 | RSI: {signals['rsi']:.1f}")

            # 포지션 있음
            if self.position:
                price = signals['price']
                buy_price = self.position['buy_price']
                profit_rate = (price - buy_price) / buy_price

                # 최고/최저 업데이트
                if profit_rate > self.position_peak_profit:
                    self.position_peak_profit = profit_rate
                if profit_rate < self.position_lowest_profit:
                    self.position_lowest_profit = profit_rate

                # 포지션 보유 시간
                hold_hours = (datetime.now() - self.position['buy_time']).total_seconds() / 3600
                hold_minutes = hold_hours * 60

                self.log(f"포지션: {profit_rate*100:+.2f}% (최고: {self.position_peak_profit*100:+.2f}%) | 보유: {hold_hours:.1f}h")

                # === 시간대별 파라미터 동적 조절 ===
                session = TimeBasedStrategy.get_trading_session()
                base_params = {
                    'quick_profit': self.quick_profit,
                    'take_profit_1': self.take_profit_1,
                    'rsi_buy': self.rsi_buy
                }
                adjusted_params = TimeBasedStrategy.adjust_parameters(base_params, session)

                # 조절된 파라미터 사용
                quick_profit_adj = adjusted_params['quick_profit']
                take_profit_1_adj = adjusted_params['take_profit_1']

                # === 다층 익절 시스템 (시간대별 조절) ===
                # 1. 퀵 익절 (30분 이내, 시간대별 조절)
                if hold_minutes <= 30 and profit_rate >= quick_profit_adj:
                    self.sell(status, signals, f"⚡ 퀵익절 ({profit_rate*100:.2f}%, {session['name']})")

                # 2. 최종 익절 (4%)
                elif profit_rate >= self.take_profit_3:
                    self.sell(status, signals, f"🎯 최종익절 ({profit_rate*100:.2f}%)")

                # 3. 2차 익절 (2.5%)
                elif profit_rate >= self.take_profit_2:
                    self.sell(status, signals, f"✅ 2차익절 ({profit_rate*100:.2f}%)")

                # 4. 1차 익절 (시간대별 조절)
                elif profit_rate >= take_profit_1_adj:
                    self.sell(status, signals, f"✅ 1차익절 ({profit_rate*100:.2f}%, {session['name']})")

                # === 손절 ===
                elif profit_rate <= self.stop_loss:
                    self.sell(status, signals, f"❌ 손절 ({profit_rate*100:.2f}%)")

                # === 동적 트레일링 스톱 ===
                # 1.5% 이상 수익 시: -0.8% 트레일링
                elif self.position_peak_profit >= 0.015 and profit_rate < self.position_peak_profit - self.trailing_stop_wide:
                    self.sell(status, signals, f"📉 트레일링스톱-와이드 (최고 {self.position_peak_profit*100:.2f}%)")

                # 0.8% 이상 수익 시: -0.5% 트레일링
                elif self.position_peak_profit >= 0.008 and profit_rate < self.position_peak_profit - self.trailing_stop_medium:
                    self.sell(status, signals, f"📉 트레일링스톱-미디엄 (최고 {self.position_peak_profit*100:.2f}%)")

                # 0.3% 이상 수익 시: -0.3% 트레일링 (핵심 개선!)
                elif self.position_peak_profit >= 0.003 and profit_rate < self.position_peak_profit - self.trailing_stop_tight:
                    self.sell(status, signals, f"📉 트레일링스톱-타이트 (최고 {self.position_peak_profit*100:.2f}%)")

                # === 포지션 타임아웃 ===
                # 3시간 이상 보유 + 손실 중이면 청산
                elif hold_hours >= self.position_timeout_hours and profit_rate < 0:
                    self.sell(status, signals, f"⏰ 타임아웃청산 ({hold_hours:.1f}h, {profit_rate*100:.2f}%)")

                # 3시간 이상 보유 + 수익 미미하면 청산
                elif hold_hours >= self.position_timeout_hours and profit_rate < 0.005:
                    self.sell(status, signals, f"⏰ 타임아웃청산 ({hold_hours:.1f}h, {profit_rate*100:.2f}%)")

                # === RSI 과열 신호 ===
                elif signals['sell'] and profit_rate > 0:
                    self.sell(status, signals, f"📊 RSI과열 ({profit_rate*100:.2f}%)")
            
            # 포지션 없음
            else:
                if signals['buy']:
                    self.buy(status, signals)
            
            self.error_count = 0
            
        except Exception as e:
            self.error_count += 1
            self.log(f"오류: {e}")
            if self.error_count >= 3:
                self.telegram.send_message(f"⚠️ 연속 오류 {self.error_count}회\n{e}")
    
    def daily_report(self):
        """일일 리포트"""
        try:
            status = self.get_current_status()
            
            today = datetime.now().date()
            today_trades = [t for t in self.trade_history if t['time'].date() == today]
            
            buys = sum(1 for t in today_trades if t['type'] == 'BUY')
            sells = sum(1 for t in today_trades if t['type'] == 'SELL')
            today_profit = sum(t.get('profit', 0) for t in today_trades if t['type'] == 'SELL')
            
            all_sells = [t for t in self.trade_history if t['type'] == 'SELL']
            total_profit = sum(t.get('profit', 0) for t in all_sells)
            wins = sum(1 for t in all_sells if t.get('profit', 0) > 0)
            win_rate = (wins / len(all_sells) * 100) if all_sells else 0
            
            msg = f"📊 <b>일일 리포트</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 자산:\n"
            msg += f"  • 총: {status['total']:,.0f}원\n"
            msg += f"  • 원화: {status['krw']:,.0f}원\n"
            msg += f"  • 코인: {status['coin_value']:,.0f}원\n\n"
            msg += f"📈 오늘:\n"
            msg += f"  • 거래: {len(today_trades)}회\n"
            msg += f"  • 손익: {today_profit:+,.0f}원\n\n"
            
            if self.position:
                profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
                msg += f"💼 포지션:\n"
                msg += f"  • 수익률: {profit_rate:+.2f}%\n\n"
            
            msg += f"📊 전체:\n"
            msg += f"  • 총거래: {len(all_sells)}회\n"
            msg += f"  • 누적: {total_profit:+,.0f}원\n"
            msg += f"  • 승률: {win_rate:.1f}%\n"
            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            self.telegram.send_message(msg)
            self.log("📊 일일 리포트")
            
        except Exception as e:
            self.log(f"리포트 실패: {e}")
    
    def check_daily_report(self):
        """오후 9시 리포트"""
        now = datetime.now()
        if now.hour == 21 and now.minute < 5:
            if not self.last_daily_report or self.last_daily_report.date() < now.date():
                self.daily_report()
                self.last_daily_report = now
    
    def handle_command(self, command):
        """명령어 처리 (비동기)"""
        try:
            cmd = command.lower()
            # 즉시 응답 전송 (사용자 경험 개선)
            self.telegram.send_message("⏳ 처리 중...")

            if cmd == '/status':
                self.send_status()
            elif cmd == '/report':
                self.daily_report()
            elif cmd == '/position':
                self.send_position_info()
            elif cmd == '/market':
                self.send_market_info()
            elif cmd == '/trend':
                self.send_trend_info()
            elif cmd == '/help':
                self.send_help()
            else:
                self.telegram.send_message(f"❌ 알 수 없는 명령어\n/help 입력")
        except Exception as e:
            self.telegram.send_message(f"명령어 처리 실패: {e}")
    
    def send_status(self):
        """현재 상태"""
        try:
            status = self.get_current_status()
            signals = self.get_signals(self.signal_timeframe)

            msg = f"📊 <b>현재 상태</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 총자산: {status['total']:,.0f}원\n"
            msg += f"💵 원화: {status['krw']:,.0f}원\n"
            msg += f"🪙 코인: {status['coin']:.6f} ETH\n\n"
            
            if self.position:
                profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
                msg += f"💼 포지션: {profit_rate:+.2f}%\n\n"
            else:
                msg += f"💼 포지션 없음\n\n"
            
            if signals:
                msg += f"📈 시장:\n"
                msg += f"  • RSI: {signals['rsi']:.1f}\n"
                msg += f"  • 볼린저: {signals['bb_pos']:.1f}%\n\n"
            
            msg += f"🤖 봇: 정상 작동\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self.telegram.send_message(msg)
            
        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_position_info(self):
        """포지션 정보"""
        try:
            if not self.position:
                self.telegram.send_message("💼 포지션 없음")
                return
            
            status = self.get_current_status()
            profit_rate = (status['current_price'] - self.position['buy_price']) / self.position['buy_price'] * 100
            
            msg = f"💼 <b>포지션</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 매수가: {self.position['buy_price']:,.0f}원\n"
            msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
            msg += f"💵 수익률: {profit_rate:+.2f}%\n\n"
            msg += f"🎯 익절: {self.position['buy_price']*1.05:,.0f}원\n"
            msg += f"🎯 손절: {self.position['buy_price']*0.97:,.0f}원"
            
            self.telegram.send_message(msg)
            
        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_market_info(self):
        """시장 정보"""
        try:
            status = self.get_current_status()
            signals = self.get_signals(self.signal_timeframe)

            if not signals:
                self.telegram.send_message("시장 정보 없음")
                return

            msg = f"📈 <b>시장</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
            msg += f"📊 24시간: {status['change_24h']:+.2f}%\n\n"

            if signals.get('trend'):
                trend = signals['trend']
                trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
                trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}
                state = trend['trend_state']
                msg += f"🌐 추세: {trend_emoji.get(state, '📊')} {trend_name.get(state, state)}\n"
                msg += f"  • 1H: {'↑' if trend['trend_1h'] == 'up' else '↓'}\n"
                msg += f"  • 4H: {'↑' if trend['trend_4h'] == 'up' else '↓'}\n\n"

            msg += f"📊 {self.signal_timeframe}분봉:\n"
            msg += f"  • RSI: {signals['rsi']:.1f}\n"
            msg += f"  • 볼린저: {signals['bb_pos']:.1f}%\n"
            msg += f"  • 거래량: {signals['vol_ratio']:.2f}x\n\n"

            if signals['buy']:
                msg += f"🟢 매수 신호!"
            elif signals['sell']:
                msg += f"🔴 매도 신호!"
            else:
                msg += f"⚪ 대기"

            self.telegram.send_message(msg)

        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")

    def send_trend_info(self):
        """추세 상세 정보"""
        try:
            trend = self.get_trend_analysis()

            if not trend:
                self.telegram.send_message("추세 정보 없음")
                return

            trend_emoji = {"strong_bull": "🚀", "correction": "📊", "weak_bounce": "⚡", "strong_bear": "🔻"}
            trend_name = {"strong_bull": "강한상승", "correction": "조정", "weak_bounce": "약한반등", "strong_bear": "강한하락"}
            state = trend['trend_state']

            msg = f"🌐 <b>추세 분석</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 현재: {trend_emoji.get(state, '📊')} <b>{trend_name.get(state, state)}</b>\n\n"

            msg += f"⏱️ 1시간봉:\n"
            msg += f"  • 추세: {'↑ 상승' if trend['trend_1h'] == 'up' else '↓ 하락'}\n"
            msg += f"  • RSI: {trend['rsi_1h']:.1f}\n"
            msg += f"  • MA20: {trend['ma20_1h']:,.0f}원\n"
            msg += f"  • MA50: {trend['ma50_1h']:,.0f}원\n\n"

            msg += f"⏱️ 4시간봉:\n"
            msg += f"  • 추세: {'↑ 상승' if trend['trend_4h'] == 'up' else '↓ 하락'}\n"
            msg += f"  • RSI: {trend['rsi_4h']:.1f}\n"
            msg += f"  • MA20: {trend['ma20_4h']:,.0f}원\n"
            msg += f"  • MA50: {trend['ma50_4h']:,.0f}원\n\n"

            msg += f"🎯 전략:\n"
            msg += f"  • 매수: {'✅ 가능' if trend['buy_allowed'] else '❌ 금지'}\n"
            msg += f"  • RSI 기준: < {trend['rsi_threshold']}\n"

            self.telegram.send_message(msg)

        except Exception as e:
            self.telegram.send_message(f"조회 실패: {e}")
    
    def send_help(self):
        """도움말"""
        msg = f"🤖 <b>명령어</b>\n━━━━━━━━━━━━━━━━━\n\n"
        msg += f"/status - 현재 상태\n"
        msg += f"/position - 포지션\n"
        msg += f"/market - 시장 현황\n"
        msg += f"/trend - 추세 분석\n"
        msg += f"/report - 일일 리포트\n"
        msg += f"/help - 도움말\n\n"
        msg += f"⚙️ 다층 익절 전략:\n"
        msg += f"  • ⚡ 퀵익절: +{self.quick_profit*100:.1f}% (30분내)\n"
        msg += f"  • 1차: +{self.take_profit_1*100:.1f}%\n"
        msg += f"  • 2차: +{self.take_profit_2*100:.1f}%\n"
        msg += f"  • 최종: +{self.take_profit_3*100:.0f}%\n\n"
        msg += f"🛡️ 리스크 관리:\n"
        msg += f"  • 손절: {self.stop_loss*100:.1f}%\n"
        msg += f"  • 동적 트레일링: 0.3/0.5/0.8%\n"
        msg += f"  • 타임아웃: {self.position_timeout_hours}h\n\n"
        msg += f"📊 추세별 매수 (1H+4H):\n"
        msg += f"  • 🚀 강한상승: RSI < 50\n"
        msg += f"  • 📊 조정: RSI < 45\n"
        msg += f"  • ⚡ 약한반등: RSI < 40\n"
        msg += f"  • 🔻 강한하락: RSI < 30"

        self.telegram.send_message(msg)
    
    def check_telegram_commands(self):
        """명령어 체크 (백그라운드 처리)"""
        try:
            updates = self.telegram.get_updates(self.last_update_id)

            if not updates or 'result' not in updates:
                return

            for update in updates['result']:
                self.last_update_id = update['update_id'] + 1

                if 'message' in update and 'text' in update['message']:
                    text = update['message']['text'].strip()

                    if text.startswith('/'):
                        self.log(f"명령어: {text}")
                        # 백그라운드로 실행하여 메인 루프 차단 방지
                        self.executor.submit(self.handle_command, text)

        except Exception as e:
            pass
    
    def initialize(self):
        """초기화"""
        try:
            status = self.get_current_status()
            
            self.log(f"\n{'='*50}")
            self.log(f"초기화")
            self.log(f"원화: {status['krw']:,.0f}원")
            self.log(f"코인: {status['coin']:.6f} ETH")
            self.log(f"총자산: {status['total']:,.0f}원")
            
            # 기존 코인
            if status['coin'] >= 0.001:
                buy_price = status['avg_price'] if status['avg_price'] > 0 else status['current_price']
                
                self.position = {
                    'buy_price': buy_price,
                    'buy_time': datetime.now(),
                    'amount': status['coin'],
                    'buy_krw': status['coin'] * buy_price
                }
                
                profit_rate = (status['current_price'] - buy_price) / buy_price * 100
                
                msg = f"💼 <b>기존 포지션</b>\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"🪙 {status['coin']:.6f} ETH\n"
                msg += f"📊 매수가: {buy_price:,.0f}원\n"
                msg += f"📊 현재가: {status['current_price']:,.0f}원\n"
                msg += f"💵 수익률: {profit_rate:+.2f}%\n\n"
                msg += f"✅ 감시 시작!"
                
                self.telegram.send_message(msg)
                self.log("✅ 기존 포지션")
            
            else:
                mode_tag = "🧪 [시뮬레이션 모드]" if self.dry_run else ""
                msg = f"💰 <b>봇 시작</b> {mode_tag}\n━━━━━━━━━━━━━━━━━\n\n"
                msg += f"💵 원화: {status['krw']:,.0f}원\n"
                msg += f"✅ 매수 신호 대기\n\n"
                msg += f"⚙️ 다층 익절 전략:\n"
                msg += f"  • 다중 시간대 분석 (1H + 4H)\n"
                msg += f"  • 익절: ⚡{self.quick_profit*100:.1f}% / {self.take_profit_1*100:.1f}% / {self.take_profit_2*100:.1f}% / {self.take_profit_3*100:.0f}%\n"
                msg += f"  • 손절: {abs(self.stop_loss)*100:.1f}%\n"
                msg += f"  • 동적 트레일링 & 타임아웃 {self.position_timeout_hours}h"

                self.telegram.send_message(msg)
                self.log("✅ 신호 대기")
                
        except Exception as e:
            self.log(f"초기화 실패: {e}")
    
    def log(self, msg):
        """로그"""
        print(msg)
    
    def run(self, interval=300):
        """실행"""
        self.initialize()
        self.send_help()

        self.log(f"\n🤖 봇 시작 ({interval}초 체크)")

        try:
            while self.is_running:
                self.check_and_trade()
                self.check_daily_report()
                self.check_telegram_commands()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.log("\n봇 종료")
            self.telegram.send_message("⏹️ 봇 중지")
        finally:
            # 백그라운드 작업 정리
            self.executor.shutdown(wait=True)


# ===== 실행 =====
if __name__ == "__main__":
    from config import get_config

    try:
        # .env 파일에서 설정 로드
        config = get_config()

        # 멀티 코인 모드 활성화 여부 (환경변수로 제어)
        enable_multi_coin = os.environ.get('ENABLE_MULTI_COIN', 'true').lower() == 'true'

        print("✅ 설정 로드 완료")
        print(f"Market: {config['market']}")
        print(f"Check Interval: {config['check_interval']}초")
        print(f"멀티 코인 모드: {'ON' if enable_multi_coin else 'OFF'}\n")

        # 실행
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])
        bot = TradingBot(
            upbit,
            telegram,
            config['market'],
            enable_multi_coin=enable_multi_coin
        )
        bot.run(config['check_interval'])

    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        print("\n.env 파일을 확인해주세요.")