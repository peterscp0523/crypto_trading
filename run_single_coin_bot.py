"""
단일 코인 집중 전략 봇
멀티코인 제거, 1개 코인에 90% 집중 투자
"""
import os
import time
from telegram_bot import TelegramBot, TradingBot
from upbit_api import UpbitAPI
from database_manager import DatabaseManager
from auto_coin_selector import AutoCoinSelector
from config import get_config


if __name__ == "__main__":
    try:
        config = get_config()

        print("=" * 60)
        print("🎯 단일 코인 집중 전략 봇 시작 (자동 코인 선택)")
        print("=" * 60)
        print(f"⚠️  멀티 코인 모드: OFF (단일 코인 집중)")
        print(f"🔄 자동 코인 선택: 10분마다")
        print(f"⏱️  체크 간격: {config['check_interval']}초")
        print(f"💰 포지션 크기: 90% (1개 코인만)")
        print(f"🎯 익절: 0.2% / 0.35% / 0.5% / 0.8%")
        print(f"🛑 손절: -0.2% ~ -0.25%")

        # 데이터베이스 (선택적)
        use_oracle = os.environ.get('USE_ORACLE_DB', 'false').lower() == 'true'
        db = None
        if use_oracle or os.environ.get('USE_DB', 'false').lower() == 'true':
            try:
                db = DatabaseManager(use_oracle=use_oracle)
                print(f"✅ 데이터베이스: {'Oracle Cloud' if use_oracle else 'SQLite'}")
            except Exception as e:
                print(f"⚠️ DB 연동 실패, DB 없이 실행: {e}")
                db = None
        else:
            print(f"ℹ️  데이터베이스 미사용 (메모리 모드)")

        print("=" * 60)
        print()

        # API 초기화
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

        # 자동 코인 선택기
        coin_selector = AutoCoinSelector(upbit)

        # 최초 코인 선택
        selected_market = coin_selector.select_best_coin()
        if not selected_market:
            print("❌ 초기 코인 선택 실패, 기본 마켓 사용")
            selected_market = config['market']

        # 봇 실행 (멀티 코인 모드 비활성화)
        bot = TradingBot(
            upbit,
            telegram,
            selected_market,
            dry_run=False,
            signal_timeframe=1,
            enable_multi_coin=False,  # 멀티 코인 OFF
            db=db
        )

        # 코인 선택기를 봇에 연결 (자동 전환용)
        bot.coin_selector = coin_selector

        # 시작 메시지
        db_status = f"💾 DB: {'Oracle' if use_oracle else 'SQLite' if db else '미사용'}\\n" if db else ""
        telegram.send_message(
            f"🎯 <b>단일 코인 집중 봇 시작</b>\\n"
            f"━━━━━━━━━━━━━━━━━\\n\\n"
            f"💰 1개 코인만 90% 집중 투자\\n"
            f"🔄 자동 코인 선택: 10분마다\\n"
            f"🎯 익절: 0.2% / 0.35% / 0.5% / 0.8%\\n"
            f"🛑 손절: -0.2% ~ -0.25%\\n"
            f"⏱️  체크: {config['check_interval']}초마다\\n"
            f"{db_status}\\n"
            f"선택된 마켓: {selected_market}"
        )

        bot.run(config['check_interval'])

    except KeyboardInterrupt:
        print("\\n봇 종료됨")
    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
