"""
긴급 전략 수정
현재 문제: 과도한 분산 + 익절 조건 너무 높음 + 손절 작동 안함
"""
from upbit_api import UpbitAPI
from config import get_config
from telegram_bot import TelegramBot
import time

def emergency_close_positions():
    """현재 포지션 즉시 정리 (손실 최소화)"""
    config = get_config()
    upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
    telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

    accounts = upbit.get_accounts()

    print("=" * 70)
    print("🚨 긴급 포지션 정리")
    print("=" * 70)

    total_loss = 0

    for acc in accounts:
        currency = acc['currency']
        balance = float(acc['balance'])
        avg_buy_price = float(acc['avg_buy_price'])

        if currency == 'KRW' or balance == 0:
            continue

        market = f'KRW-{currency}'

        try:
            ticker = upbit.get_current_price(market)
            current_price = ticker['trade_price']
            current_value = balance * current_price

            if avg_buy_price > 0:
                profit = current_value - (balance * avg_buy_price)
                profit_pct = (profit / (balance * avg_buy_price)) * 100

                # 손실이 -0.3% 이상이면 즉시 매도
                if profit_pct < -0.3:
                    print(f"\n❌ {currency} 손절 매도: {profit_pct:.2f}%")
                    result = upbit.order_market_sell(market, balance)

                    if result and 'uuid' in result:
                        print(f"  ✅ 매도 완료: {balance:.8f}개 @ {current_price:,.0f}원")
                        total_loss += profit

                        telegram.send_message(
                            f"🚨 <b>손절 매도</b>\n"
                            f"━━━━━━━━━━━━━━━━━\n\n"
                            f"코인: {market}\n"
                            f"수량: {balance:.8f}\n"
                            f"손익: {profit:+,.0f}원 ({profit_pct:+.2f}%)\n\n"
                            f"이유: 전략 실패, 포지션 정리"
                        )
                    else:
                        print(f"  ❌ 매도 실패: {result}")

                    time.sleep(0.3)

                # 이익이 +0.1% 이상이면 즉시 익절
                elif profit_pct > 0.1:
                    print(f"\n💰 {currency} 익절 매도: {profit_pct:.2f}%")
                    result = upbit.order_market_sell(market, balance)

                    if result and 'uuid' in result:
                        print(f"  ✅ 매도 완료: {balance:.8f}개 @ {current_price:,.0f}원")
                        total_loss += profit

                        telegram.send_message(
                            f"💰 <b>익절 매도</b>\n"
                            f"━━━━━━━━━━━━━━━━━\n\n"
                            f"코인: {market}\n"
                            f"수량: {balance:.8f}\n"
                            f"손익: {profit:+,.0f}원 ({profit_pct:+.2f}%)\n\n"
                            f"이유: 빠른 익절"
                        )
                    else:
                        print(f"  ❌ 매도 실패: {result}")

                    time.sleep(0.3)

                # -0.3% ~ +0.1% 범위는 보류 (변동성 대기)
                else:
                    print(f"\n⏸️  {currency} 보류: {profit_pct:.2f}% (변동성 대기)")

        except Exception as e:
            print(f"  ❌ {currency} 처리 실패: {e}")

    print()
    print("=" * 70)
    print(f"총 손익: {total_loss:+,.0f}원")
    print("=" * 70)


if __name__ == "__main__":
    emergency_close_positions()
