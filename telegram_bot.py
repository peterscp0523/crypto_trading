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
from market_regime import MarketRegimeDetector  # Tier 3 개선
from execution_manager import ExecutionManager  # Phase 1: 주문 실행 최적화
from risk_manager import RiskManager  # Phase 1: VaR 리스크 관리
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
    
    def __init__(self, upbit, telegram, market="KRW-ETH", dry_run=False, signal_timeframe=1,
                 enable_multi_coin=False, db=None):
        self.upbit = upbit
        self.telegram = telegram
        self.market = market
        self.dry_run = dry_run  # 시뮬레이션 모드
        self.signal_timeframe = signal_timeframe  # 신호 타임프레임 (1, 5, 15, 60분)
        self.enable_multi_coin = enable_multi_coin  # 멀티 코인 모드
        self.db = db  # 데이터베이스 매니저 (선택적)

        # 전략 파라미터 (다층 익절 시스템) - 실전 최적화
        self.rsi_buy = 42            # 30 → 35 → 42 (실전 최적화: 더 자주 매수)
        self.rsi_sell = 70           # 70 유지

        # 다층 익절 전략 (빠른 수익 실현) - 기본값
        self.quick_profit = 0.008    # 0.8% 퀵 익절 (30분 이내)
        self.take_profit_1 = 0.015   # 1.5% 1차 익절
        self.take_profit_2 = 0.025   # 2.5% 2차 익절
        self.take_profit_3 = 0.04    # 4.0% 최종 익절

        self.stop_loss = -0.015      # -2% → -1.5% (더 빠른 손절, 기본값)

        # Tier 2 개선: 적응형 손절 (변동성 기반)
        self.adaptive_stop_loss = True  # 적응형 손절 활성화
        self.stop_loss_min = -0.008     # 최소 손절: -0.8% (저변동성)
        self.stop_loss_max = -0.015     # 최대 손절: -1.5% (고변동성)

        # Tier 2 개선: 시간 기반 익절 완화
        self.time_based_profit_relaxation = True  # 시간 기반 익절 완화 활성화
        self.relaxation_time_minutes = 30         # 30분 이후 완화
        self.profit_relaxation_amount = 0.003     # -0.3%p 완화

        # 부분 익절 전략 (Tier 1 개선)
        self.enable_partial_sell = True  # 부분 익절 활성화
        self.partial_sell_ratios = [
            (0.015, 0.50),  # 1.5% 도달 시 50% 매도
            (0.025, 0.30),  # 2.5% 도달 시 30% 매도 (남은 것의)
            (0.040, 0.20),  # 4.0% 도달 시 20% 매도 (남은 것의)
        ]

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

        # Tier 3 개선: 시장 상태 감지
        self.market_regime_detector = MarketRegimeDetector(upbit)
        self.use_market_regime = True  # 시장 상태 기반 조정 활성화

        # Phase 1: 기관급 실행 및 리스크 관리
        self.execution_manager = ExecutionManager(upbit)
        self.risk_manager = RiskManager(upbit)
        self.enable_limit_orders = True  # 지정가 주문 활성화
        self.limit_order_strategy = 'mid'  # 'best', 'mid', 'aggressive'

        # 상태
        self.position = None
        self.trade_history = []
        self.is_running = True
        self.error_count = 0
        self.last_daily_report = None
        self.position_peak_profit = 0
        self.position_lowest_profit = 0
        self.last_update_id = None
        # 리소스 최적화: Always Free Tier (1 OCPU)에 맞게 조정
        self.executor = ThreadPoolExecutor(max_workers=1)

        # 일일 손실 제한 (Tier 1 개선)
        self.max_daily_loss = -0.03  # -3%
        self.daily_pnl = 0
        self.daily_pnl_reset_date = datetime.now().date()
        self.trading_paused = False
        self.consecutive_losses = 0  # 연속 손실 카운트

        # 동적 스캔 빈도 (Tier 1 개선)
        self.base_check_interval = 300  # 기본 5분
        self.current_check_interval = 300
        self.last_atr_check = None

        # Tier 4 개선: 실시간 파라미터 최적화
        self.auto_optimize = True  # 자동 최적화 활성화
        self.last_optimization_date = None  # 마지막 최적화 날짜
        self.optimization_interval_days = 7  # 7일마다 재최적화

        # 리소스 최적화: 신호 캐싱 (1 OCPU VM 대응)
        self.signal_cache = {}  # {timeframe: (timestamp, signals)}
        self.signal_cache_duration = 10  # 10초간 캐시 유지 (1분봉 대응)

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
        """시장 분석 및 신호 (다중 시간대 포함, Tier 1 개선: 스마트 볼륨 필터)

        리소스 최적화: 캐싱으로 불필요한 API 호출 감소

        Args:
            timeframe: 5, 15, 60 등 (분 단위)
        """
        # 캐시 확인 (리소스 최적화)
        now = datetime.now()
        cache_key = f"{self.market}_{timeframe}"
        if cache_key in self.signal_cache:
            cached_time, cached_signals = self.signal_cache[cache_key]
            if (now - cached_time).total_seconds() < self.signal_cache_duration:
                return cached_signals

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
        vol_ratio = current_vol / vol_ma

        # 다중 시간대 추세 분석
        trend = self.get_trend_analysis()

        # === 스마트 볼륨 필터 (실전 최적화 - 거래량 대폭 완화) ===
        # 시간대별 동적 임계값 (거래량 조건 대폭 완화)
        if timeframe == 1:
            base_vol_threshold = 0.3  # 1분봉: 1.2 → 0.3 (매우 완화)
        elif timeframe == 5:
            base_vol_threshold = 0.3  # 5분봉: 1.0 → 0.3 (매우 완화)
        elif timeframe == 15:
            base_vol_threshold = 0.3  # 15분봉: 0.95 → 0.3 (매우 완화)
        else:
            base_vol_threshold = 0.3  # 더 긴 시간대: 0.9 → 0.3 (매우 완화)

        # 추세 강할 때 더욱 완화 (0.5배)
        if trend and trend['trend_state'] in ['strong_bull', 'correction']:
            vol_threshold = base_vol_threshold * 0.5  # 0.15배까지 허용
        else:
            vol_threshold = base_vol_threshold

        # 거래량 조건 체크
        volume_ok = vol_ratio >= vol_threshold

        # 매수 조건 (실전 최적화: 거래량 조건 제거, RSI+볼린저만 사용)
        buy_signal = False
        if trend and trend['buy_allowed']:
            rsi_threshold = trend['rsi_threshold']

            # 추세별 조건 (실전 최적화: 거래량 조건 완전 제거)
            if trend['trend_state'] == 'strong_bull':
                # 강한 상승: RSI만
                buy_signal = (rsi < rsi_threshold)
            elif trend['trend_state'] == 'correction':
                # 조정: RSI + 볼린저 완화
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.20)
            elif trend['trend_state'] == 'weak_bounce':
                # 약한 반등: RSI + 볼린저 완화 (거래량 조건 제거)
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.15)
            elif trend['trend_state'] == 'strong_bear':
                # 강한 하락: 과매도 + 볼린저 완화 (거래량 조건 제거)
                buy_signal = (rsi < rsi_threshold and current_price <= lower * 1.10)
        else:
            # 추세 분석 실패: 과매도 + 볼린저 완화
            buy_signal = (rsi < 35 and current_price <= lower * 1.10)

        signals = {
            'price': current_price,
            'rsi': rsi,
            'upper': upper,
            'lower': lower,
            'bb_pos': bb_pos,
            'vol_ratio': vol_ratio,
            'vol_threshold': vol_threshold,  # 현재 적용된 임계값
            'volume_ok': volume_ok,  # 볼륨 조건 충족 여부
            'trend': trend,
            'buy': buy_signal,
            'sell': rsi > self.rsi_sell and current_price >= upper * 0.99
        }

        # 캐시 저장 (리소스 최적화)
        self.signal_cache[cache_key] = (now, signals)

        return signals
    
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

            # === Phase 1: 리스크 한도 체크 (VaR) ===
            total_portfolio_krw = krw  # 전체 포트폴리오 가치
            risk_check = self.risk_manager.check_risk_limits(position_krw, total_portfolio_krw, self.market)

            if not risk_check.get('approved'):
                self.log(f"⚠️ 리스크 한도 초과: {risk_check.get('reason')}")
                return False

            # === Phase 1: 슬리피지 추정 ===
            slippage_data = None
            execution_quality = ""
            if self.enable_limit_orders:
                slippage_data = self.execution_manager.estimate_slippage(self.market, 'buy', position_krw)
                if slippage_data:
                    execution_quality = f"\n📊 예상 슬리피지: {slippage_data['estimated_slippage']:.3f}%"
                    execution_quality += f"\n💡 {slippage_data['recommendation']}"

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                amount = position_krw / price
                self.virtual_coin = amount
                self.virtual_krw = krw - position_krw
                self.virtual_avg_price = price
                executed_price = price
            # 실제 주문
            else:
                # Phase 1: 지정가 주문 시도 (슬리피지가 클 경우)
                if self.enable_limit_orders and slippage_data and slippage_data['estimated_slippage'] > 0.10:
                    # 슬리피지 > 0.1%면 지정가 사용
                    order_result = self.execution_manager.execute_limit_order(
                        self.market, 'buy', position_krw,
                        price_strategy=self.limit_order_strategy,
                        max_wait_seconds=20
                    )

                    if order_result.get('success'):
                        executed_price = order_result['price']
                        amount = order_result['volume']
                        execution_quality += f"\n✅ 지정가 체결 ({order_result.get('execution_time', 0):.1f}초)"
                    else:
                        # 지정가 실패시 시장가 폴백 (이미 내부 처리됨)
                        executed_price = price
                        amount = position_krw / price
                else:
                    # 시장가 주문
                    result = self.upbit.order_market_buy(self.market, position_krw)
                    executed_price = price
                    amount = position_krw / price
                    execution_quality += "\n📍 시장가 체결"

            self.position = {
                'buy_price': executed_price if not self.dry_run else price,
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

            # 시장 상태 가져오기
            market_regime = None
            if self.use_market_regime and self.market_regime_detector.current_regime:
                market_regime = self.market_regime_detector.current_regime

            # 다중 시간대 신호 강도
            signal_strength = ""
            if 'buy_signal_count' in signals:
                count = signals['buy_signal_count']
                if count == 3:
                    signal_strength = "🔥 매우 강함"
                elif count == 2:
                    signal_strength = "✅ 강함"
                else:
                    signal_strength = "⚠️ 약함"

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}🔵 <b>매수 완료</b>\n"
            msg += f"{'='*30}\n\n"

            # 코인 정보
            msg += f"🪙 <b>{self.market.replace('KRW-', '')}</b>\n"
            msg += f"💰 <b>{price:,.0f}원</b> × {amount:.6f}\n"
            msg += f"💵 투자금: <b>{position_krw:,.0f}원</b> ({position_krw/krw*100:.0f}% 사용)\n"
            msg += f"💼 잔액: {krw - position_krw:,.0f}원\n\n"

            # 시간 및 세션 정보
            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            msg += f"📅 {session['name']} (공격성: {session['aggression']}, 변동성: {session['volatility']})\n\n"

            # 시장 상태 (Tier 3)
            if market_regime:
                regime_emoji = {"bull": "🐂", "bear": "🐻", "sideways": "↔️"}
                msg += f"🌍 <b>시장 상태</b>\n"
                msg += f"  • {regime_emoji.get(market_regime['regime'])} {market_regime['regime'].upper()}"
                msg += f" (신뢰도: {market_regime['strength']:.0f}%)\n"
                msg += f"  • BTC 추세: {market_regime['btc_trend'].upper()}"
                msg += f" (RSI: {market_regime['btc_rsi_1h']:.1f})\n"
                msg += f"  • 시장 심리: {market_regime['market_sentiment']:.0f}%\n\n"

            # 매수 신호 강도 (Tier 2)
            if signal_strength:
                msg += f"📶 <b>신호 강도</b>: {signal_strength}\n"
                msg += f"  • 1분봉: {'✅' if signals['multi_timeframe']['1m']['buy'] else '❌'}\n"
                msg += f"  • 5분봉: {'✅' if signals['multi_timeframe']['5m']['buy'] else '❌'}\n"
                msg += f"  • 15분봉: {'✅' if signals['multi_timeframe']['15m']['buy'] else '❌'}\n\n"

            # 추세 분석
            if signals.get('trend'):
                trend = signals['trend']
                state = trend['trend_state']
                msg += f"📈 <b>추세 분석</b>\n"
                msg += f"  • 상태: {trend_emoji.get(state, '📊')} {trend_name.get(state, state)}\n"
                msg += f"  • 1H: {'🔼' if trend['trend_1h'] == 'up' else '🔽'} RSI {trend['rsi_1h']:.1f}"
                msg += f" (MA20: {trend['ma20_1h']:,.0f})\n"
                msg += f"  • 4H: {'🔼' if trend['trend_4h'] == 'up' else '🔽'} RSI {trend['rsi_4h']:.1f}"
                msg += f" (MA20: {trend['ma20_4h']:,.0f})\n\n"

            # 기술적 지표
            msg += f"📊 <b>기술적 지표</b>\n"
            msg += f"  • RSI(15m): {signals['rsi']:.1f}"
            msg += f" ({'과매도' if signals['rsi'] < 30 else '중립' if signals['rsi'] < 70 else '과매수'})\n"
            msg += f"  • 볼린저밴드: {signals['bb_pos']:.1f}%"
            msg += f" ({'하단' if signals['bb_pos'] < 20 else '중간' if signals['bb_pos'] < 80 else '상단'})\n"
            msg += f"  • 거래량: {signals['vol_ratio']:.2f}x"
            msg += f" (기준: {signals.get('vol_threshold', 1.2):.2f}x)"
            if signals.get('volume_ok'):
                msg += " ✅\n"
            else:
                msg += " ⚠️\n"
            msg += f"  • 가격: {price:,.0f}원\n"
            msg += f"  • 상한: {signals['upper']:,.0f}원 (+{((signals['upper']-price)/price)*100:.1f}%)\n"
            msg += f"  • 하한: {signals['lower']:,.0f}원 ({((signals['lower']-price)/price)*100:.1f}%)\n\n"

            # 익절 목표 (부분 익절 포함)
            msg += f"🎯 <b>익절 목표</b> (부분 익절 전략)\n"
            msg += f"  • ⚡ 퀵 (30분): {price * (1 + self.quick_profit):,.0f}원"
            msg += f" (+{self.quick_profit*100:.1f}%) → 100% 매도\n"
            msg += f"  • 🥉 1차: {price * (1 + self.take_profit_1):,.0f}원"
            msg += f" (+{self.take_profit_1*100:.1f}%) → 50% 매도\n"
            msg += f"  • 🥈 2차: {price * (1 + self.take_profit_2):,.0f}원"
            msg += f" (+{self.take_profit_2*100:.1f}%) → 30% 매도\n"
            msg += f"  • 🥇 최종: {price * (1 + self.take_profit_3):,.0f}원"
            msg += f" (+{self.take_profit_3*100:.0f}%) → 100% 매도\n\n"

            # 리스크 관리 (VaR 추가 - Phase 1)
            adaptive_sl = self.get_adaptive_stop_loss() if hasattr(self, 'get_adaptive_stop_loss') else self.stop_loss
            msg += f"🛡️ <b>리스크 관리</b>\n"
            msg += f"  • 손절: {price * (1 + adaptive_sl):,.0f}원"
            msg += f" ({adaptive_sl*100:.2f}%)"
            if self.adaptive_stop_loss:
                msg += " 📊 적응형\n"
            else:
                msg += "\n"
            msg += f"  • 트레일링 스톱:\n"
            msg += f"    - 0.3% 도달 → -0.3% 트레일링\n"
            msg += f"    - 0.8% 도달 → -0.5% 트레일링\n"
            msg += f"    - 1.5% 도달 → -0.8% 트레일링\n"
            msg += f"  • 타임아웃: {self.position_timeout_hours}시간\n"
            msg += f"  • 일일 손익: {self.daily_pnl*100:.2f}% (한도: {self.max_daily_loss*100:.0f}%)\n"

            # Phase 1: VaR 정보
            var_data = self.risk_manager.calculate_var(self.market, confidence_level=0.95)
            if var_data:
                msg += f"  • VaR(95%, 1일): -{var_data['var_1day']:.2f}% (최대 예상 손실)\n"
                msg += f"  • 변동성: {var_data['volatility']:.2f}%\n"
            msg += "\n"

            # Phase 1: 실행 품질
            if execution_quality:
                msg += f"⚡ <b>실행 품질</b>{execution_quality}\n\n"

            # 거래 통계
            if len(self.trade_history) > 1:
                recent_trades = self.trade_history[-10:]
                wins = sum(1 for t in recent_trades if t.get('profit', 0) > 0)
                win_rate = (wins / len(recent_trades)) * 100 if recent_trades else 0
                msg += f"📈 <b>최근 거래 성과</b> (최근 {len(recent_trades)}건)\n"
                msg += f"  • 승률: {win_rate:.0f}% ({wins}승 {len(recent_trades)-wins}패)\n\n"

            msg += f"{'='*30}"
            
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

            # 수익 여부에 따른 이모지
            if profit > 0:
                emoji = "🟢"
                result_text = "익절 성공"
            else:
                emoji = "🔴"
                result_text = "손절 실행"

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}{emoji} <b>매도 완료 - {result_text}</b>\n"
            msg += f"{'='*30}\n\n"

            # 코인 및 거래 정보
            msg += f"🪙 <b>{self.market.replace('KRW-', '')}</b>\n"
            msg += f"💰 매도가: <b>{price:,.0f}원</b>\n"
            msg += f"📈 매수가: {buy_price:,.0f}원\n"
            msg += f"📊 수량: {coin:.6f}\n\n"

            # 수익 정보 (강조)
            profit_emoji = "💰" if profit > 0 else "💸"
            msg += f"{profit_emoji} <b>{'수익' if profit > 0 else '손실'}</b>\n"
            msg += f"  • 금액: <b>{profit:+,.0f}원</b>\n"
            msg += f"  • 수익률: <b>{profit_rate:+.2f}%</b>\n"
            if profit > 0:
                expected_amount = sell_krw + profit
                msg += f"  • 총 회수: {sell_krw:,.0f}원\n\n"
            else:
                msg += f"  • 총 회수: {sell_krw:,.0f}원\n\n"

            # 보유 기간 및 성과
            hold_days = int(hold_hours // 24)
            remaining_hours = hold_hours % 24
            msg += f"⏱️ <b>보유 기간</b>\n"
            if hold_days > 0:
                msg += f"  • {hold_days}일 {remaining_hours:.1f}시간\n"
            else:
                msg += f"  • {hold_hours:.1f}시간\n"
            msg += f"  • 최고 수익률: {self.position_peak_profit*100:+.2f}%\n"
            msg += f"  • 최저 수익률: {self.position_lowest_profit*100:+.2f}%\n"

            # 수익 포기 계산 (최고점 대비)
            if self.position_peak_profit > 0:
                missed_profit = (self.position_peak_profit - (profit_rate/100)) * 100
                if missed_profit > 0:
                    msg += f"  • 최고점 대비: -{missed_profit:.2f}%p ⬇️\n"
            msg += "\n"

            # 매도 사유
            msg += f"📝 <b>매도 사유</b>: {reason}\n\n"

            # 현재 시장 상태
            msg += f"📊 <b>시장 정보</b>\n"
            msg += f"  • RSI: {signals['rsi']:.1f}"
            msg += f" ({'과매도' if signals['rsi'] < 30 else '중립' if signals['rsi'] < 70 else '과매수'})\n"
            msg += f"  • 가격 위치: {signals['bb_pos']:.0f}%"
            msg += f" ({'하단' if signals['bb_pos'] < 20 else '중간' if signals['bb_pos'] < 80 else '상단'})\n\n"

            # 일일 손익 업데이트
            projected_daily_pnl = (self.daily_pnl + (profit / 1000000)) * 100
            msg += f"📈 <b>일일 누적</b>\n"
            msg += f"  • 오늘 손익: {projected_daily_pnl:+.2f}%"
            if projected_daily_pnl > 0:
                msg += " 🔥\n"
            elif projected_daily_pnl < -2:
                msg += " ⚠️\n"
            else:
                msg += "\n"
            msg += f"  • 일일 한도: {self.max_daily_loss*100:.0f}%\n\n"

            # 최근 거래 성과
            recent_trades = [t for t in self.trade_history if t.get('type') == 'SELL'][-10:]
            if len(recent_trades) >= 3:
                wins = sum(1 for t in recent_trades if t.get('profit', 0) > 0)
                total_profit = sum(t.get('profit', 0) for t in recent_trades)
                avg_profit_rate = sum(t.get('profit_rate', 0) for t in recent_trades) / len(recent_trades) * 100
                win_rate = (wins / len(recent_trades)) * 100

                msg += f"📊 <b>최근 성과</b> (최근 {len(recent_trades)}건)\n"
                msg += f"  • 승률: {win_rate:.0f}% ({wins}승 {len(recent_trades)-wins}패)\n"
                msg += f"  • 평균 수익률: {avg_profit_rate:+.2f}%\n"
                msg += f"  • 누적 수익: {total_profit:+,.0f}원\n\n"

            msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            msg += f"{'='*30}"
            
            self.telegram.send_message(msg)
            self.log("✅ 매도 완료")
            
            self.position = None
            self.position_peak_profit = 0
            self.position_lowest_profit = 0
            
            # 일일 손실 업데이트
            self.update_daily_pnl(profit)

            return True

        except Exception as e:
            self.log(f"❌ 매도 실패: {e}")
            self.telegram.send_message(f"❌ 매도 실패: {e}")
            return False

    def partial_sell(self, status, signals, ratio, reason):
        """부분 매도 실행 (Tier 1 개선)"""
        if not self.position:
            return False

        coin = status['coin']
        if coin < 0.001:
            return False

        try:
            price = signals['price']
            buy_price = self.position['buy_price']
            profit_rate = (price - buy_price) / buy_price * 100

            # 매도할 수량 계산
            sell_amount = coin * ratio

            # 너무 적은 양은 거래하지 않음
            if sell_amount < 0.001:
                return False

            # 드라이런 모드: 가상 거래
            if self.dry_run:
                sell_krw = sell_amount * price
                self.virtual_coin -= sell_amount
                self.virtual_krw += sell_krw
            # 실제 주문
            else:
                self.upbit.order_market_sell(self.market, sell_amount)

            sell_krw = sell_amount * price
            profit = sell_krw - (self.position['buy_krw'] * ratio)

            # 포지션 업데이트
            self.position['sold_amount'] = self.position.get('sold_amount', 0) + sell_amount

            mode_prefix = "🧪 [시뮬레이션] " if self.dry_run else ""
            msg = f"{mode_prefix}📊 <b>부분 매도 ({ratio*100:.0f}%)</b>\n━━━━━━━━━━━━━━━━━\n\n"
            msg += f"💰 금액: {sell_krw:,.0f}원\n"
            msg += f"📊 가격: {price:,.0f}원\n"
            msg += f"📈 매수가: {buy_price:,.0f}원\n\n"
            msg += f"💵 <b>수익: {profit:+,.0f}원 ({profit_rate:+.2f}%)</b>\n\n"
            msg += f"📝 사유: {reason}\n"
            msg += f"💼 남은 포지션: {(1-ratio-self.position.get('sold_ratio', 0))*100:.0f}%\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"

            self.telegram.send_message(msg)
            self.log(f"✅ 부분 매도 완료 ({ratio*100:.0f}%)")

            # 판매 비율 누적
            self.position['sold_ratio'] = self.position.get('sold_ratio', 0) + ratio

            # 일일 손실 업데이트
            self.update_daily_pnl(profit)

            return True

        except Exception as e:
            self.log(f"❌ 부분 매도 실패: {e}")
            return False

    def update_daily_pnl(self, profit):
        """일일 손익 업데이트 (Tier 1 개선)"""
        # 날짜가 바뀌면 리셋
        today = datetime.now().date()
        if today != self.daily_pnl_reset_date:
            self.daily_pnl = 0
            self.daily_pnl_reset_date = today
            self.trading_paused = False
            self.consecutive_losses = 0
            self.log("📅 일일 손익 리셋")

        # 손익 업데이트
        profit_rate = profit / 1000000  # 100만원 기준 손익률
        self.daily_pnl += profit_rate

        # 연속 손실 추적
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # 일일 손실 제한 체크
        if self.daily_pnl <= self.max_daily_loss:
            self.trading_paused = True
            msg = f"⚠️ <b>일일 손실 제한 도달</b>\n\n"
            msg += f"오늘 손익: {self.daily_pnl*100:.2f}%\n"
            msg += f"제한: {self.max_daily_loss*100:.0f}%\n\n"
            msg += f"내일까지 거래가 중단됩니다."
            self.telegram.send_message(msg)
            self.log(f"⚠️ 거래 중단: 일일 손실 {self.daily_pnl*100:.2f}%")

    def get_adaptive_stop_loss(self):
        """적응형 손절 레벨 계산 (Tier 2 개선)

        변동성(ATR)에 따라 손절 레벨 동적 조정:
        - 저변동성: 타이트한 손절 (-0.8%)
        - 고변동성: 넓은 손절 (-1.5%)
        """
        if not self.adaptive_stop_loss:
            return self.stop_loss

        try:
            # ATR 계산 (1시간봉 기준)
            from advanced_features import VolatilityManager
            candles = self.upbit.get_candles(self.market, "minutes", 60, 30)

            if not candles or len(candles) < 14:
                return self.stop_loss  # 데이터 부족 시 기본값

            atr = VolatilityManager.calculate_atr(candles, period=14)
            current_price = candles[0]['trade_price']
            atr_percent = (atr / current_price) * 100

            # 변동성 기반 손절 레벨 결정
            if atr_percent < 2:
                # 저변동성: 타이트한 손절
                adaptive_stop = self.stop_loss_min
            elif atr_percent > 4:
                # 고변동성: 넓은 손절
                adaptive_stop = self.stop_loss_max
            else:
                # 중간: 선형 보간
                ratio = (atr_percent - 2) / (4 - 2)
                adaptive_stop = self.stop_loss_min + (self.stop_loss_max - self.stop_loss_min) * ratio

            self.log(f"🎯 적응형 손절: {adaptive_stop*100:.2f}% (ATR: {atr_percent:.2f}%)")
            return adaptive_stop

        except Exception as e:
            self.log(f"적응형 손절 계산 실패: {e}")
            return self.stop_loss

    def check_multi_coin_switch(self):
        """멀티 코인 모드: 더 나은 코인으로 전환 검토"""
        if not self.enable_multi_coin or not self.market_scanner:
            return False

        # 포지션 없을 때만 코인 변경 고려
        if self.position:
            return False

        # 1분봉 대응: 2분마다 스캔 (1분봉 2번 체크 후 재평가)
        now = datetime.now()
        if self.last_coin_scan and (now - self.last_coin_scan).total_seconds() < 120:
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

    def scan_multi_coin_buy_signals(self, top_n=5):
        """멀티 코인 매수 신호 동시 스캔 (1분봉 최적화)

        TOP 5 모멘텀 코인을 동시에 체크하여 가장 강한 매수 신호를 찾음
        """
        try:
            # 모멘텀 랭킹 가져오기 (2분마다 갱신)
            if (not self.market_scanner.last_scan_time or
                (datetime.now() - self.market_scanner.last_scan_time).total_seconds() > 120):
                self.market_scanner.scan_top_coins(top_n=20, min_volume_100m=50)

            if not self.market_scanner.cached_rankings:
                return None

            # TOP N 코인의 매수 신호 체크
            best_signal = None
            best_score = 0

            for coin in self.market_scanner.cached_rankings[:top_n]:
                market = coin['market']

                # 현재 마켓 임시 변경하여 신호 체크
                original_market = self.market
                self.market = market

                # 다중 시간대 신호 분석
                signals = self.get_multi_timeframe_signals()

                # 마켓 복원
                self.market = original_market

                if not signals:
                    continue

                # 강한 매수 신호인지 체크
                buy_signal_count = signals.get('buy_signal_count', 0)

                # 매수 신호 점수: (매수신호 강도 * 10) + 모멘텀 점수
                signal_score = (buy_signal_count * 10) + coin['score']

                # 최소 1개 이상 시간대에서 매수 신호 필요 (2개 → 1개로 완화)
                if buy_signal_count >= 1 and signal_score > best_score:
                    best_score = signal_score
                    best_signal = {
                        'market': market,
                        'name': coin['name'],
                        'signals': signals,
                        'buy_signal_count': buy_signal_count,
                        'momentum_score': coin['score'],
                        'total_score': signal_score
                    }

            if best_signal:
                self.log(f"🎯 최강 매수 신호: {best_signal['name']} (신호: {best_signal['buy_signal_count']}/3, 모멘텀: {best_signal['momentum_score']})")

            return best_signal

        except Exception as e:
            self.log(f"멀티 코인 스캔 실패: {e}")
            return None

    def get_multi_timeframe_signals(self):
        """다중 시간대 신호 분석 (Tier 2 개선)

        1분/5분/15분을 모두 체크하여 신호 강도 판단
        """
        try:
            # 각 시간대별 신호 가져오기
            signals_1m = self.get_signals(1)
            signals_5m = self.get_signals(5)
            signals_15m = self.get_signals(15)

            if not all([signals_1m, signals_5m, signals_15m]):
                return None

            # 매수 신호 강도 계산
            buy_signals = [
                signals_1m['buy'],
                signals_5m['buy'],
                signals_15m['buy']
            ]
            buy_signal_count = sum(buy_signals)

            # 매도 신호 강도 계산
            sell_signals = [
                signals_1m['sell'],
                signals_5m['sell'],
                signals_15m['sell']
            ]
            sell_signal_count = sum(sell_signals)

            # 강한 신호: 2개 이상 동의
            strong_buy = buy_signal_count >= 2
            strong_sell = sell_signal_count >= 2

            # 매우 강한 신호: 3개 모두 동의
            very_strong_buy = buy_signal_count == 3
            very_strong_sell = sell_signal_count == 3

            # 15분봉을 기본으로 사용하되, 다중 시간대 정보 추가
            base_signals = signals_15m.copy()
            base_signals.update({
                'multi_timeframe': {
                    '1m': signals_1m,
                    '5m': signals_5m,
                    '15m': signals_15m
                },
                'buy_signal_count': buy_signal_count,
                'sell_signal_count': sell_signal_count,
                'strong_buy': strong_buy,
                'strong_sell': strong_sell,
                'very_strong_buy': very_strong_buy,
                'very_strong_sell': very_strong_sell,
                # 기존 buy/sell을 강한 신호로 대체
                'buy': strong_buy,
                'sell': strong_sell
            })

            return base_signals

        except Exception as e:
            self.log(f"다중 시간대 분석 실패: {e}")
            # 실패 시 기본 15분봉으로 fallback
            return self.get_signals(15)

    def check_and_trade(self):
        """메인 로직 (Tier 2+3 개선: 다중 시간대 + 시장 상태)"""
        try:
            # 일일 손실 제한 체크 (Tier 1 개선)
            if self.trading_paused:
                self.log(f"⏸️ 거래 중단: 일일 손실 {self.daily_pnl*100:.2f}%")
                return

            # Tier 3 개선: 시장 상태 감지
            market_regime = None
            if self.use_market_regime:
                # 10분마다 시장 상태 체크
                if not self.market_regime_detector.last_check_time or \
                   (datetime.now() - self.market_regime_detector.last_check_time).total_seconds() > 600:
                    market_regime = self.market_regime_detector.detect_market_regime()
                    if market_regime:
                        regime_emoji = {"bull": "🐂", "bear": "🐻", "sideways": "↔️"}
                        self.log(f"{regime_emoji.get(market_regime['regime'])} 시장: {market_regime['regime'].upper()} "
                                f"(신뢰도: {market_regime['strength']:.0f}%, BTC RSI: {market_regime['btc_rsi_1h']:.1f})")

                # 약세장이 매우 강할 때도 과매도 반등 매수 허용
                bear_market_active = market_regime and market_regime['regime'] == 'bear' and market_regime['strength'] > 80
                btc_rsi = market_regime.get('btc_rsi_1h', 50) if market_regime else 50

                if bear_market_active:
                    self.log(f"🐻 강한 약세장 (BTC RSI: {btc_rsi:.1f}) - 과매도 반등만 매수")

            status = self.get_current_status()

            # 멀티 코인 모드: 포지션 없을 때 TOP 5 코인 동시 매수 신호 체크
            if self.enable_multi_coin and not self.position and self.market_scanner:
                best_buy_signal = self.scan_multi_coin_buy_signals()

                # 약세장에서는 더 강한 신호 요구 (3/3 만족)
                if bear_market_active and best_buy_signal:
                    if best_buy_signal['buy_signal_count'] < 3:
                        self.log(f"⚠️ 약세장: 매수 신호 약함 ({best_buy_signal['buy_signal_count']}/3) - 대기")
                        best_buy_signal = None

                if best_buy_signal:
                    # 가장 강한 매수 신호가 나온 코인으로 즉시 전환
                    if best_buy_signal['market'] != self.market:
                        self.log(f"💱 즉시 전환: {self.market.replace('KRW-', '')} → {best_buy_signal['name']} (매수신호 강도: {best_buy_signal['buy_signal_count']}/3)")
                        self.market = best_buy_signal['market']
                    signals = best_buy_signal['signals']
                else:
                    # 매수 신호 없으면 기존 로직 (코인 전환 검토)
                    self.check_multi_coin_switch()
                    signals = self.get_multi_timeframe_signals()
            else:
                # 포지션 있거나 싱글 코인 모드: 현재 코인만 체크
                signals = self.get_multi_timeframe_signals()

            if not signals:
                self.log("신호 없음")
                return

            self.log(f"\n[{datetime.now().strftime('%H:%M:%S')}] 체크 ({self.market.replace('KRW-', '')})")
            self.log(f"자산: {status['total']:,.0f}원 | RSI: {signals['rsi']:.1f}")

            # Tier 2: 다중 시간대 신호 강도 로그
            if 'buy_signal_count' in signals:
                self.log(f"📊 매수신호: {signals['buy_signal_count']}/3 (1m/5m/15m)"
                        f"{' 🔥' if signals.get('very_strong_buy') else ' ✅' if signals.get('strong_buy') else ''}")

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

                # Tier 2 개선: 적응형 손절 레벨 계산
                adaptive_stop_loss = self.get_adaptive_stop_loss()

                # === 부분 익절 시스템 (Tier 1 + Tier 2 개선) ===
                if self.enable_partial_sell:
                    sold_ratio = self.position.get('sold_ratio', 0)

                    # Tier 2: 시간 기반 익절 완화 (30분 이후 임계값 낮춤)
                    tp1_threshold = self.take_profit_1
                    tp2_threshold = self.take_profit_2
                    tp3_threshold = self.take_profit_3

                    if self.time_based_profit_relaxation and hold_minutes > self.relaxation_time_minutes:
                        tp1_threshold -= self.profit_relaxation_amount  # 1.5% → 1.2%
                        tp2_threshold -= self.profit_relaxation_amount  # 2.5% → 2.2%
                        tp3_threshold -= self.profit_relaxation_amount  # 4.0% → 3.7%
                        self.log(f"⏱️ 익절 완화: 30분 경과 (1차: {tp1_threshold*100:.1f}%, 2차: {tp2_threshold*100:.1f}%, 3차: {tp3_threshold*100:.1f}%)")

                    # 1. 퀵 익절 (30분 이내, 시간대별 조절) - 전체 매도
                    if hold_minutes <= 30 and profit_rate >= quick_profit_adj:
                        self.sell(status, signals, f"⚡ 퀵익절 ({profit_rate*100:.2f}%, {session['name']})")

                    # 2. 1차 익절 (1.5% 또는 완화된 임계값) - 50% 부분 매도
                    elif profit_rate >= tp1_threshold and sold_ratio < 0.5:
                        self.partial_sell(status, signals, 0.50, f"✅ 1차익절 50% ({profit_rate*100:.2f}%)")

                    # 3. 2차 익절 (2.5% 또는 완화된 임계값) - 추가 30% 부분 매도
                    elif profit_rate >= tp2_threshold and sold_ratio < 0.8:
                        remaining = 1.0 - sold_ratio
                        ratio = 0.30 / (1.0 - 0.5) if sold_ratio >= 0.5 else 0.30
                        self.partial_sell(status, signals, min(ratio, remaining), f"✅ 2차익절 30% ({profit_rate*100:.2f}%)")

                    # 4. 최종 익절 (4% 또는 완화된 임계값) - 남은 전부 매도
                    elif profit_rate >= tp3_threshold:
                        self.sell(status, signals, f"🎯 최종익절 ({profit_rate*100:.2f}%)")

                # 기존 방식 (부분 익절 비활성화 시)
                else:
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

                    # === 손절 (Tier 2: 적응형) ===
                    elif profit_rate <= adaptive_stop_loss:
                        self.sell(status, signals, f"❌ 손절 ({profit_rate*100:.2f}%, 임계값: {adaptive_stop_loss*100:.2f}%)")

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
    
    def update_check_interval(self):
        """동적 스캔 빈도 업데이트 (Tier 1 개선)"""
        # 5분마다 변동성 체크
        now = datetime.now()
        if self.last_atr_check and (now - self.last_atr_check).total_seconds() < 300:
            return

        self.last_atr_check = now

        try:
            # ATR 계산을 위한 데이터 가져오기
            from advanced_features import VolatilityManager
            candles = self.upbit.get_candles(self.market, 15, 30)  # 15분봉 30개
            if not candles or len(candles) < 14:
                return

            atr = VolatilityManager.calculate_atr(candles, period=14)
            if not atr:
                return

            current_price = candles[0]['trade_price']
            atr_percent = (atr / current_price) * 100

            # 변동성 기반 동적 간격
            if atr_percent > 4:
                self.current_check_interval = 120  # 2분 (고변동성)
            elif atr_percent > 2:
                self.current_check_interval = 180  # 3분 (중변동성)
            else:
                self.current_check_interval = 300  # 5분 (저변동성)

            # 포지션 보유 중이면 더 자주 체크
            if self.position:
                self.current_check_interval = min(self.current_check_interval, 60)  # 최대 1분

            self.log(f"⏱️ 스캔 간격 업데이트: {self.current_check_interval}초 (ATR: {atr_percent:.2f}%)")

        except Exception as e:
            self.log(f"스캔 간격 업데이트 실패: {e}")

    def run(self, interval=300):
        """실행 (Tier 1 개선: 동적 스캔 빈도)"""
        self.initialize()
        self.send_help()
        self.base_check_interval = interval
        self.current_check_interval = interval

        self.log(f"\n🤖 봇 시작 (기본 {interval}초 체크, 동적 조절 활성화)")

        try:
            while self.is_running:
                # 동적 스캔 빈도 업데이트
                self.update_check_interval()

                self.check_and_trade()
                self.check_daily_report()
                self.check_telegram_commands()

                # 동적으로 조절된 간격으로 대기
                time.sleep(self.current_check_interval)
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