#!/usr/bin/env python3
"""Radmir: одна блокировка на запуск, музыку и временные настройки экрана."""
import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import audio
import common
import display
import settings


def session_paths():
    key = hashlib.sha256(str(settings.PREFIX).encode()).hexdigest()[:16]
    root = common.STATE / 'sessions' / key
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root/'audio-restore.json', root/'display-restore.json'


def check():
    problems = []
    for title, path in [('Лаунчер', settings.launcher()), ('Proton', settings.RUNNER/'proton'),
                        ('UMU', common.DATA/'umu-run')]:
        print(title + ': ' + str(path))
        if not path.is_file():
            problems.append(title)
    for binary in ['flatpak']:
        if not __import__('shutil').which(binary):
            problems.append(binary)
    if problems:
        raise ValueError('Не найдены компоненты: ' + ', '.join(problems) + '. Запустите bash install.sh.')
    common.call(['flatpak', 'info', common.APP], stdout=subprocess.DEVNULL)
    from install import native_ready
    if not native_ready():
        raise ValueError('Не все библиотеки графики готовы. Повторите bash install.sh.')
    print('Основные файлы найдены. Вход в игру, графика и звук проверяются при запуске.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true', help='вернуть настройки после прерванного сеанса')
    parser.add_argument('--no-audio-fix', action='store_true')
    parser.add_argument('--no-display-fix', action='store_true')
    parser.add_argument('--prefix', type=Path)
    args = parser.parse_args()
    if os.getuid() == 0:
        raise ValueError('Запускайте без sudo')
    settings.configure(args.prefix)
    if args.check:
        return check()
    if not args.restore:
        check()
    with common.operation_lock():
        display.require_closed()
        logs = common.STATE/'logs'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-session')
        logs.mkdir(parents=True, mode=0o700)
        proxy_marker, display_marker = session_paths()
        # Recover interrupted state before starting a new proxy or changing screens.
        audio.recover(proxy_marker, logs)
        display.recover(display_marker)
        if args.restore:
            print('Сохранённые настройки сеанса восстановлены. Игра не запускалась.')
            return 0
        with audio.session(proxy_marker, logs, enabled=not args.no_audio_fix):
            with display.temporary_fullhd(display_marker, logs, enabled=not args.no_display_fix):
                return settings.run(settings.launcher(), logs)


def interrupted(signum, frame):
    raise KeyboardInterrupt


if __name__ == '__main__':
    os.umask(0o077)
    for sig in [signal.SIGTERM, signal.SIGHUP]:
        signal.signal(sig, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit('ОСТАНОВЛЕНО: ' + str(exc))
