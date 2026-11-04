"""Временная обработка музыкальных URL с восстановлением трёх параметров реестра."""
from contextlib import contextmanager
import json
from http.server import ThreadingHTTPServer
import re
import subprocess
import threading
import common
import settings
from audio_proxy import SessionHandler

KEY = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
NAMES = ('ProxyEnable', 'ProxyServer', 'ProxyOverride')


def snapshot():
    active = False
    values = {}
    section = '[' + KEY.replace('\\', '\\\\') + ']'
    for line in (settings.PREFIX/'user.reg').read_text().splitlines():
        if line.startswith('['):
            active = line.split(']', 1)[0] + ']' == section
        if active:
            match = re.match(r'"([^"]+)"=(.*)$', line)
            if match and match[1] in NAMES:
                values[match[1]] = match[2]
    return values


def registry(values, logs, label):
    if any(k not in NAMES or not isinstance(v, str) or '\n' in v or '\r' in v for k,v in values.items()):
        raise ValueError('Некорректные сохранённые настройки прокси')
    path = logs / (label + '.reg')
    lines = ['Windows Registry Editor Version 5.00', '', '[HKEY_CURRENT_USER\\' + KEY + ']']
    lines += ['"' + name + '"=' + values.get(name, '-') for name in NAMES]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-16')
    args = settings.command('reg.exe', logs,
                            ['import', 'Z:' + str(path).replace('/', '\\')], hud=False)
    with (logs/(label+'.log')).open('w') as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, timeout=90)
    if result.returncode:
        raise ValueError('Не удалось применить ' + label + '. Журнал: ' + str(logs))


def recover(marker, logs):
    if not marker.exists():
        return
    saved = json.loads(marker.read_text())
    if saved.get('prefix') != str(settings.PREFIX):
        raise ValueError('План восстановления прокси относится к другому префиксу')
    registry(saved['values'], logs, 'restore-proxy')
    marker.unlink()
    print('Прежние сетевые настройки Radmir восстановлены.', flush=True)


@contextmanager
def session(marker, logs, enabled=True):
    if not enabled:
        yield
        return
    old = snapshot()
    common.atomic(marker, json.dumps({'prefix': str(settings.PREFIX), 'values': old}) + '\n')
    server = None
    worker = None
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 0), SessionHandler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        address = '127.0.0.1:' + str(server.server_address[1])
        registry({'ProxyEnable': 'dword:00000001',
                  'ProxyServer': '"http=' + address + ';https=' + address + '"',
                  'ProxyOverride': '"<local>"'}, logs, 'enable-proxy')
        print('Включена обработка адресов музыки с кириллицей.', flush=True)
        yield
    finally:
        # Keep the marker if restoring Wine settings fails, for the next launch.
        try:
            recover(marker, logs)
        finally:
            if server:
                if worker and worker.ident is not None and worker.is_alive():
                    server.shutdown()
                server.server_close()
            if worker:
                worker.join(timeout=5)
