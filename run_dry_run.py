"""
드라이런 모드 실행 스크립트
실제 거래 없이 시뮬레이션만 진행
"""
from upbit_api import UpbitAPI
from telegram_bot import TelegramBot, TradingBot


if __name__ == "__main__":
    from config import get_config

    print("\n" + "="*60)
    print("🧪 드라이런 모드 - 시뮬레이션 봇")
    print("="*60)
    print("\n⚠️  이 모드는 실제 거래를 하지 않습니다.")
    print("⚠️  가상 잔고 100만원으로 시뮬레이션합니다.\n")

    try:
        # .env 파일에서 설정 로드
        config = get_config()

        print("✅ 설정 로드 완료")
        print(f"Market: {config['market']}")
        print(f"Check Interval: {config['check_interval']}초\n")

        # 실행
        upbit = UpbitAPI(config['upbit_access_key'], config['upbit_secret_key'])
        telegram = TelegramBot(config['telegram_token'], config['telegram_chat_id'])

        # 드라이런 모드로 봇 생성
        bot = TradingBot(upbit, telegram, config['market'], dry_run=True)

        print("✅ 드라이런 모드 봇 시작\n")
        print("📋 명령어:")
        print("   /status - 현재 상태")
        print("   /market - 시장 현황")
        print("   /trend - 추세 분석")
        print("   /report - 리포트")
        print("\n🛑 종료: Ctrl+C\n")

        bot.run(config['check_interval'])

    except Exception as e:
        print(f"❌ 봇 시작 실패: {e}")
        print("\n.env 파일을 확인해주세요.")
