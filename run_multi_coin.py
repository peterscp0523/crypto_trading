"""
멀티 코인 모멘텀 봇 실행
모멘텀이 강한 코인을 자동으로 선택하여 거래
"""
from telegram_bot import TelegramBot, TradingBot
from upbit_api import UpbitAPI
from config import get_config


if __name__ == "__main__":
    try:
        # 설정 로드
        config = get_config()

        print("=" * 60)
        print("🚀 멀티 코인 모멘텀 봇 시작")
        print("=" * 60)
        print(f"✅ 멀티 코인 모드: ON")
        print(f"📊 초기 마켓: {config['market']}")
        print(f"⏱️  체크 간격: {config['check_interval']}초")
        print(f"🔍 코인 스캔: 10분마다")
        print("=" * 60)
        print()

        # API 초기화
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

        # 봇 실행 (멀티 코인 모드 활성화)
        bot = TradingBot(
            upbit,
            telegram,
            config['market'],
            dry_run=False,  # 실전 모드
            signal_timeframe=15,
            enable_multi_coin=True  # 멀티 코인 모드
        )

        # 시작 메시지
        telegram.send_message(
            f"🚀 <b>멀티 코인 봇 시작</b>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 모멘텀이 강한 코인을 자동 선택합니다\n"
            f"🔄 10분마다 코인 재평가\n"
            f"📊 거래량 상위 20개 코인 분석\n\n"
            f"초기 마켓: {config['market']}"
        )

        bot.run(config['check_interval'])

    except KeyboardInterrupt:
        print("\n봇 종료됨")
    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
