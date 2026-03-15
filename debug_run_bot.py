# Temporary debug runner — calls bot_start.main() with exception printing
import traceback
import sys

try:
    import bot_start
    print('Imported bot_start OK')
    print('TELEGRAM_TOKEN present:', bool(bot_start.TELEGRAM_TOKEN))
    print('Starting bot_start.main()...')
    bot_start.main()
except Exception:
    traceback.print_exc()
    sys.exit(1)

