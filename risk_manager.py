"""
리스크 관리자 (Institutional-Level Phase 1)
- VaR (Value at Risk) 계산
- 포지션 리스크 모니터링
- 포트폴리오 리스크 측정
"""
import numpy as np
from datetime import datetime, timedelta


class RiskManager:
    """포트폴리오 리스크 관리"""

    def __init__(self, upbit):
        self.upbit = upbit
        self.historical_returns = {}  # {market: [returns]}

    def calculate_var(self, market, confidence_level=0.95, lookback_days=30, method='historical'):
        """
        VaR (Value at Risk) 계산

        Args:
            market: 마켓 (KRW-BTC)
            confidence_level: 신뢰 수준 (0.95 = 95%)
            lookback_days: 과거 데이터 기간 (일)
            method:
                - 'historical': 과거 수익률 분포 기반
                - 'parametric': 정규분포 가정 (평균, 표준편차)
                - 'monte_carlo': 몬테카를로 시뮬레이션

        Returns:
            dict: {
                'var_1day': float (% 손실),
                'cvar_1day': float (% 조건부 VaR),
                'volatility': float (% 일일 변동성),
                'interpretation': str
            }
        """
        try:
            # 과거 캔들 데이터 수집 (1일봉)
            candles = self.upbit.get_candles(market, "days", 1, lookback_days + 1)

            if not candles or len(candles) < lookback_days:
                return None

            # 일일 수익률 계산
            returns = []
            for i in range(len(candles) - 1):
                price_today = candles[i]['trade_price']
                price_yesterday = candles[i + 1]['trade_price']
                daily_return = (price_today - price_yesterday) / price_yesterday
                returns.append(daily_return)

            returns = np.array(returns)

            # 메서드별 VaR 계산
            if method == 'historical':
                # Historical VaR: 과거 수익률 분포에서 분위수
                var_1day = -np.percentile(returns, (1 - confidence_level) * 100)

            elif method == 'parametric':
                # Parametric VaR: 정규분포 가정
                mean_return = np.mean(returns)
                std_return = np.std(returns)

                # Z-score (95% = 1.645, 99% = 2.326)
                z_score = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}.get(confidence_level, 1.645)

                var_1day = -(mean_return - z_score * std_return)

            else:  # monte_carlo
                # Monte Carlo VaR: 시뮬레이션
                mean_return = np.mean(returns)
                std_return = np.std(returns)

                # 10,000회 시뮬레이션
                simulated_returns = np.random.normal(mean_return, std_return, 10000)
                var_1day = -np.percentile(simulated_returns, (1 - confidence_level) * 100)

            # CVaR (Conditional VaR = Expected Shortfall)
            # VaR을 초과하는 손실의 평균
            losses = -returns[returns < -var_1day]
            cvar_1day = np.mean(losses) if len(losses) > 0 else var_1day

            # 변동성 (일일)
            volatility = np.std(returns)

            # 해석
            interpretation = self._interpret_var(var_1day, volatility)

            # 캐싱 (재사용)
            self.historical_returns[market] = returns.tolist()

            return {
                'var_1day': round(var_1day * 100, 2),  # %로 표시
                'cvar_1day': round(cvar_1day * 100, 2),
                'volatility': round(volatility * 100, 2),
                'mean_return': round(np.mean(returns) * 100, 2),
                'worst_day': round(np.min(returns) * 100, 2),
                'best_day': round(np.max(returns) * 100, 2),
                'method': method,
                'confidence_level': confidence_level,
                'lookback_days': lookback_days,
                'interpretation': interpretation
            }

        except Exception as e:
            print(f"VaR 계산 실패: {e}")
            return None

    def _interpret_var(self, var_1day, volatility):
        """VaR 해석"""
        var_pct = var_1day * 100
        vol_pct = volatility * 100

        if var_pct < 3:
            risk_level = "낮음"
        elif var_pct < 6:
            risk_level = "보통"
        elif var_pct < 10:
            risk_level = "높음"
        else:
            risk_level = "매우 높음"

        return f"리스크 수준: {risk_level} (1일 최대 예상 손실 {var_pct:.1f}%, 변동성 {vol_pct:.1f}%)"

    def calculate_position_risk(self, market, position_krw, current_price):
        """
        보유 포지션의 리스크 계산

        Args:
            market: 마켓
            position_krw: 보유 포지션 금액 (KRW)
            current_price: 현재 가격

        Returns:
            dict: {
                'position_var': float (KRW 손실),
                'position_cvar': float (KRW 손실),
                'max_loss_1day': float (KRW),
                'risk_pct_of_portfolio': float (%)
            }
        """
        var_data = self.calculate_var(market, confidence_level=0.95, method='historical')

        if not var_data:
            return None

        # 포지션 VaR (금액)
        position_var = position_krw * (var_data['var_1day'] / 100)
        position_cvar = position_krw * (var_data['cvar_1day'] / 100)

        # 최악의 날 손실
        max_loss_1day = position_krw * (abs(var_data['worst_day']) / 100)

        # 전체 포트폴리오 대비 (총 보유 KRW 계산)
        balances = self.upbit.get_balances()
        total_krw = sum(
            float(b.get('balance', 0)) * float(b.get('avg_buy_price', 0))
            for b in balances if b.get('currency') != 'KRW'
        )
        total_krw += float(next((b.get('balance', 0) for b in balances if b.get('currency') == 'KRW'), 0))

        risk_pct = (position_krw / total_krw * 100) if total_krw > 0 else 0

        return {
            'position_var': round(position_var, 0),
            'position_cvar': round(position_cvar, 0),
            'max_loss_1day': round(max_loss_1day, 0),
            'risk_pct_of_portfolio': round(risk_pct, 1),
            'var_data': var_data
        }

    def calculate_portfolio_var(self, confidence_level=0.95, correlation_adjusted=False):
        """
        포트폴리오 전체 VaR 계산

        Args:
            confidence_level: 신뢰 수준
            correlation_adjusted: 코인 간 상관관계 고려 여부

        Returns:
            dict: {
                'portfolio_var': float (KRW),
                'portfolio_cvar': float (KRW),
                'total_value': float (KRW),
                'positions': list
            }
        """
        try:
            balances = self.upbit.get_balances()

            # 코인 포지션 수집
            positions = []
            total_value = 0

            for balance in balances:
                currency = balance.get('currency')
                if currency == 'KRW':
                    krw_balance = float(balance.get('balance', 0))
                    total_value += krw_balance
                    continue

                market = f"KRW-{currency}"
                amount = float(balance.get('balance', 0))
                avg_buy_price = float(balance.get('avg_buy_price', 0))

                if amount > 0 and avg_buy_price > 0:
                    position_value = amount * avg_buy_price

                    # 개별 VaR 계산
                    var_data = self.calculate_var(market, confidence_level=confidence_level)

                    if var_data:
                        positions.append({
                            'market': market,
                            'value': position_value,
                            'var_pct': var_data['var_1day'],
                            'cvar_pct': var_data['cvar_1day']
                        })

                    total_value += position_value

            if not positions:
                return None

            # 포트폴리오 VaR 계산
            if correlation_adjusted:
                # 상관관계 고려 (간소화: 평균 상관계수 0.7 가정)
                individual_var_sum = sum(p['value'] * p['var_pct'] / 100 for p in positions)
                portfolio_var = individual_var_sum * 0.85  # 다각화 효과 15%
            else:
                # 단순 합산
                portfolio_var = sum(p['value'] * p['var_pct'] / 100 for p in positions)

            portfolio_cvar = sum(p['value'] * p['cvar_pct'] / 100 for p in positions)

            return {
                'portfolio_var': round(portfolio_var, 0),
                'portfolio_cvar': round(portfolio_cvar, 0),
                'portfolio_var_pct': round(portfolio_var / total_value * 100, 2) if total_value > 0 else 0,
                'total_value': round(total_value, 0),
                'position_count': len(positions),
                'positions': positions,
                'correlation_adjusted': correlation_adjusted
            }

        except Exception as e:
            print(f"포트폴리오 VaR 계산 실패: {e}")
            return None

    def check_risk_limits(self, position_krw, total_portfolio_krw, market):
        """
        리스크 한도 체크

        Args:
            position_krw: 신규 포지션 금액
            total_portfolio_krw: 전체 포트폴리오 가치
            market: 마켓

        Returns:
            dict: {
                'approved': bool,
                'reason': str,
                'position_size_pct': float,
                'var_check': dict
            }
        """
        try:
            # 1. 포지션 크기 제한 (단일 코인 최대 95% - 초단타용 대폭 완화)
            position_pct = (position_krw / total_portfolio_krw) * 100 if total_portfolio_krw > 0 else 0

            if position_pct > 95:
                return {
                    'approved': False,
                    'reason': f"포지션 크기 초과 ({position_pct:.1f}% > 95%)",
                    'position_size_pct': position_pct
                }

            # 2. VaR 제한 (포지션 VaR < 포트폴리오의 5%)
            var_data = self.calculate_var(market, confidence_level=0.95)

            if var_data:
                position_var = position_krw * (var_data['var_1day'] / 100)
                var_limit = total_portfolio_krw * 0.05  # 5%

                if position_var > var_limit:
                    return {
                        'approved': False,
                        'reason': f"VaR 한도 초과 ({position_var:,.0f}원 > {var_limit:,.0f}원)",
                        'position_size_pct': position_pct,
                        'var_check': {
                            'position_var': position_var,
                            'var_limit': var_limit
                        }
                    }

            # 통과
            return {
                'approved': True,
                'reason': "리스크 한도 내",
                'position_size_pct': position_pct,
                'var_check': {
                    'position_var': position_var if var_data else 0,
                    'var_limit': total_portfolio_krw * 0.05
                }
            }

        except Exception as e:
            print(f"리스크 한도 체크 실패: {e}")
            return {'approved': True, 'reason': '체크 실패 (기본 승인)'}
