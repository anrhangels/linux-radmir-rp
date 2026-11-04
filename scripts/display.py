"""Временный выбор основного Full HD экрана без смены его режима и масштаба."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import common
import settings


def processes():
    """Inspect only process owner and WINEPREFIX, never save the environment."""
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != os.getuid() or int(proc.name) == os.getpid():
                continue
            values = (proc/'environ').read_bytes().split(b'\0')
            prefix = next((v[11:] for v in values if v.startswith(b'WINEPREFIX=')), None)
            if prefix and Path(os.fsdecode(prefix)).resolve() == settings.PREFIX.resolve():
                found.append(proc.name)
        except (OSError, ValueError):
            continue
    return found


def require_closed():
    if processes():
        raise ValueError('Radmir ещё запущен. Закройте его игру и лаунчер и повторите команду.')


def query():
    result = subprocess.run(['xrandr', '--current'], capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Xwayland недоступен')
    return result.stdout


def outputs(text):
    result = {}
    for row in text.splitlines():
        match = re.match(r'^(\S+) connected (primary )?(\d+)x(\d+)[+-]', row)
        if match:
            result[match[1]] = {'primary': bool(match[2]), 'size': (int(match[3]), int(match[4]))}
    return result


def choose(data):
    return next((n for n, v in data.items() if v['primary'] and v['size'] == (1920, 1080)),
                next((n for n, v in data.items() if v['size'] == (1920, 1080)), None))


def apply_primary(previous, current):
    args = ['xrandr', '--output', previous, '--primary'] if previous in current else ['xrandr', '--noprimary']
    common.call(args, capture_output=True, text=True, timeout=8)


def recover(marker):
    if not marker.exists():
        return
    saved = json.loads(marker.read_text())
    current = outputs(query())
    # Respect a manual selection made after an interrupted session.
    if current.get(saved['selected'], {}).get('primary'):
        apply_primary(saved.get('previous'), current)
    marker.unlink()
    print('Прежний выбор основного экрана Xwayland восстановлен.', flush=True)


@contextmanager
def temporary_fullhd(marker, logs, enabled=True):
    if not enabled or not shutil.which('xrandr') or not os.environ.get('DISPLAY'):
        print('Настройка основного экрана пропущена.', flush=True)
        yield
        return
    try:
        before = query()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('Xwayland недоступен, экраны не меняются: ' + str(exc), flush=True)
        yield
        return
    data = outputs(before)
    selected = choose(data)
    previous = next((n for n, v in data.items() if v['primary']), None)
    if not selected or selected == previous:
        print('Текущие настройки экранов подходят; основной экран не меняется.', flush=True)
        yield
        return
    (logs/'xrandr-before.txt').write_text(before)
    common.atomic(marker, json.dumps({'selected': selected, 'previous': previous}) + '\n')
    try:
        common.call(['xrandr', '--output', selected, '--primary'], capture_output=True, text=True, timeout=8)
        after = query()
        (logs/'xrandr-after.txt').write_text(after)
        current = outputs(after)
        if not current.get(selected, {}).get('primary'):
            raise ValueError('Xwayland не подтвердил основной экран')
        if {k:v['size'] for k,v in current.items()} != {k:v['size'] for k,v in data.items()}:
            raise ValueError('Изменился список разрешений экранов; запуск остановлен')
        print('Временный основной экран Xwayland: ' + selected + ' (1920×1080).', flush=True)
        yield
    finally:
        recover(marker)
