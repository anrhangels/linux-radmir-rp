#!/usr/bin/env python3
"""Полная пользовательская часть установки Radmir CRMP на Linux."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import common
import settings

ROOT = Path(__file__).resolve().parents[1]
VERBS = ['ucrtbase2019', 'd3dx9_43', 'd3dcompiler_43', 'd3dcompiler_47']
DLLS = ['ucrtbase', 'd3dx9_43', 'd3dcompiler_43', 'd3dcompiler_47']


def parse_feed(text, base):
    path = re.search(r'^path:\s*(.+?)\s*$', text, re.M)
    digest = re.search(r'^sha512:\s*([\'\"]?[A-Za-z0-9+/=]+[\'\"]?)\s*$', text, re.M)
    if not path or not digest:
        raise ValueError('В официальном latest.yml не найдены path/sha512')
    relative = path[1].strip().strip('\'\"')
    expected = base64.b64decode(digest[1].strip('\'\"'), validate=True)
    if len(expected) != 64:
        raise ValueError('Неверная длина SHA-512 в latest.yml')
    url = urljoin(base, relative)
    parts = urlsplit(url)
    source = urlsplit(base)
    if (parts.scheme != 'https' or parts.hostname != source.hostname or parts.port not in (None, 443)
            or parts.username or parts.password
            or not posixpath.normpath(unquote(parts.path)).startswith(source.path)):
        raise ValueError('Неожиданный адрес официального установщика')
    encoded_path = quote(parts.path, safe='/%:@-_.~!$&\'()*+,;=')
    return {'url': urlunsplit((parts.scheme, parts.netloc, encoded_path, parts.query, '')),
            'sha512': expected.hex()}


def download_launcher(logs):
    failures = []
    for base in common.DOWNLOADS['launcher']['feeds']:
        try:
            req = Request(base + 'latest.yml', headers={'User-Agent': 'linux-radmir-rp/1.0'})
            with urlopen(req, timeout=45) as response:
                if urlsplit(response.url).scheme != 'https' or urlsplit(response.url).hostname != urlsplit(base).hostname:
                    raise ValueError('Изменился адрес официальной ленты обновления')
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Неожиданный размер latest.yml')
            common.atomic(logs/'latest.yml', raw)
            spec = parse_feed(raw.decode('utf-8-sig'), base)
            target = common.CACHE/'launchers'/spec['sha512'][:16]/'RADMIRLauncherSetup.exe'
            exe = common.fetch(spec, target)
            validate_exe(exe)
            return exe
        except (OSError, ValueError, UnicodeError) as exc:
            failures.append(str(exc))
    raise ValueError('Не удалось скачать официальный установщик: ' + '; '.join(failures))


def validate_exe(path):
    if not path.is_file():
        raise ValueError('Не найден файл установщика: ' + str(path))
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Вместо Windows EXE получен другой файл')


def native_ready():
    for directory in ['system32', 'syswow64']:
        for name in DLLS:
            file = settings.PREFIX/'drive_c/windows'/directory/(name+'.dll')
            if not file.is_file():
                return False
            with file.open('rb') as stream:
                header = stream.read(256)
            if not header.startswith(b'MZ') or b'Wine builtin DLL' in header:
                return False
    return True


def save_libraries(snapshot):
    for name in ['user.reg', 'system.reg', 'userdef.reg', 'winetricks.log']:
        snapshot.save(settings.PREFIX/name)
    for directory in ['system32', 'syswow64']:
        for name in DLLS:
            snapshot.save(settings.PREFIX/'drive_c/windows'/directory/(name+'.dll'))


def save_hud(snapshot):
    root = common.DATA/common.GAMEID
    for name in ['MangoHud.conf', 'presets.conf', 'layers/MangoHud.x86.json', 'layers/MangoHud.x86_64.json',
                 'lib/i386-linux-gnu/libMangoHud.so', 'lib/x86_64-linux-gnu/libMangoHud.so']:
        snapshot.save(root/name)


def shortcuts(snapshot):
    target = common.DATA/'tools'
    for name in ['common.py', 'settings.py', 'install.py', 'play.py', 'audio.py', 'audio_proxy.py', 'display.py', 'hud_tools.py']:
        snapshot.write(target/'scripts'/name, (ROOT/'scripts'/name).read_bytes())
    for name in ['downloads.json', 'MangoHud.conf', 'presets.conf']:
        snapshot.write(target/'configs'/name, (ROOT/'configs'/name).read_bytes())
    launcher = common.HOME/'.local/bin/radmir'
    snapshot.write(launcher, '#!/bin/sh\nexec python3 ' + shlex.quote(str(target/'scripts/play.py')) + ' "$@"\n')
    launcher.chmod(0o755)
    apps = Path(os.environ.get('XDG_DATA_HOME', common.HOME/'.local/share'))/'applications'
    command = str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    snapshot.write(apps/'linux-radmir-rp.desktop', '[Desktop Entry]\nType=Application\nName=Radmir CRMP\n'
                   'Comment=Radmir CRMP с настройками для Linux\nExec="' + command + '"\n'
                   'Icon=applications-games\nTerminal=false\nCategories=Game;\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--no-system-packages', action='store_true')
    parser.add_argument('--no-hud', action='store_true')
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--installer', type=Path)
    parser.add_argument('--windows-fonts', type=Path)
    parser.add_argument('--fonts-only', action='store_true')
    parser.add_argument('--restore', type=Path, help='восстановить файлы из снимка установки')
    args = parser.parse_args()
    settings.configure(args.prefix)
    if args.plan:
        print('Префикс:', settings.PREFIX)
        print('Подготовка: Flatpak/Faugus, GE-Proton/UMU, официальный лаунчер, UCRT, D3DX9, D3DCompiler, шрифты.')
        print('MangoHud:', 'пропустить' if args.no_hud else 'установить под runtime Faugus')
        print('План не устанавливает программы, не меняет файлы и не обращается к сети.')
        return 0
    if os.getuid() == 0:
        raise ValueError('Запускайте без sudo')
    if sys.version_info < (3, 10) or platform.machine() != 'x86_64':
        raise ValueError('Нужны Linux x86_64 и Python 3.10+')
    common.require_closed()
    with common.operation_lock():
        if args.restore:
            common.restore(args.restore)
            return 0
        for name in ['flatpak', 'fc-match', 'fc-cache']:
            if not shutil.which(name):
                raise ValueError('Не найден ' + name + '. Запустите bash install.sh.')
        snapshot = common.Snapshot()
        print('План возврата изменённых файлов: ' + str(snapshot.root/'restore.json'), flush=True)
        logs = common.STATE/'logs'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-install')
        logs.mkdir(parents=True, mode=0o700)
        common.setup_flatpak()
        runner = common.ensure_runner()
        settings.RUNNER = runner
        umu = common.fetch(common.DOWNLOADS['umu'], common.DATA/'umu-run')
        umu.chmod(0o755)
        exe = settings.launcher()
        if args.fonts_only and not exe.is_file():
            raise ValueError('Для --fonts-only нужен установленный лаунчер в выбранном префиксе')
        managed = settings.PREFIX/'.linux-radmir-rp-managed'
        if settings.PREFIX.exists() and any(settings.PREFIX.iterdir()) and not exe.is_file() and not managed.is_file():
            raise ValueError('Выбран непустой посторонний префикс; передайте другой --prefix')
        need_launcher = not exe.is_file()
        installer = None
        if need_launcher:
            installer = common.local_installer(args.installer) if args.installer else download_launcher(logs)
            validate_exe(installer)
        settings.PREFIX.mkdir(parents=True, exist_ok=True)
        common.atomic(managed, 'Created by linux-radmir-rp installer\n')
        if not args.fonts_only and not native_ready():
            save_libraries(snapshot)
            common.run_logged(settings.command('winetricks', logs, ['-q', '--force']+VERBS, hud=False), logs/'libraries.log')
            if not native_ready():
                raise ValueError('Не все библиотеки графики установлены. Журнал: ' + str(logs/'libraries.log'))
        if installer:
            print('Запускается официальный установщик. Если открылся лаунчер, закройте его для завершения настройки.', flush=True)
            common.run_logged(settings.command(installer, logs, ['/S'], hud=False), logs/'launcher-install.log')
            if not exe.is_file():
                raise ValueError('Официальный лаунчер не найден в стандартном пути. Журнал: ' + str(logs))
        common.install_fonts(settings.PREFIX, runner, logs, snapshot, args.windows_fonts)
        if args.fonts_only:
            print('Шрифты настроены. План возврата: ' + str(snapshot.root/'restore.json'))
            return 0
        common.register(exe, settings.PREFIX, runner, snapshot)
        if not args.no_hud:
            save_hud(snapshot)
            common.install_hud()
        snapshot.write(settings.PROFILE, json.dumps({'prefix': str(settings.PREFIX)}, ensure_ascii=False) + '\n')
        shortcuts(snapshot)
        print('\nГотово! Запуск: ~/.local/bin/radmir\nВыберите RADMIR CRMP в официальном лаунчере и скачайте игру.')
        print('Возврат изменённых файлов: bash install.sh --restore ' + shlex.quote(str(snapshot.root/'restore.json')))
    return 0


if __name__ == '__main__':
    os.umask(0o077)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        sys.exit('ОСТАНОВЛЕНО: ' + str(exc))
