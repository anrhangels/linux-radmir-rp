#!/usr/bin/env python3
"""Radmir CRMP: воспроизводимая установка в отдельный префикс, без системного Wine."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
APP = 'io.github.Faugus.faugus-launcher'
GAMEID = 'radmir-crmp'
DATA = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'linux-radmir-rp'
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'linux-radmir-rp'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'linux-radmir-rp'
FAUGUS = HOME / '.var/app' / APP / 'data/faugus-launcher'
LOCKFILE = STATE / 'operation.lock'
DOWNLOADS = json.loads((ROOT / 'configs/downloads.json').read_text())
FONT_KEYS = [r'Software\Microsoft\Windows NT\CurrentVersion\Fonts',
             r'Software\Microsoft\Windows\CurrentVersion\Fonts']

def call(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)

def digest_matches(path, spec):
    if not path.is_file():
        return False
    h = hashlib.sha256() if 'sha256' in spec else hashlib.sha512() if 'sha512' in spec else hashlib.sha1()
    if 'git_sha1' in spec:
        if path.stat().st_size != spec['size']:
            return False
        h.update(b'blob ' + str(path.stat().st_size).encode() + b'\0')
    with path.open('rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest() == spec.get('sha256', spec.get('sha512', spec.get('git_sha1')))

def fetch(spec, dest):
    """Pinned upstream file: no partial output and no unverified cache reuse."""
    if digest_matches(dest, spec):
        return dest
    if urlsplit(spec['url']).scheme != 'https':
        raise ValueError('Требуется HTTPS')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.part')
    print('Скачивание: ' + dest.name, flush=True)
    try:
        with urlopen(Request(spec['url'], headers={'User-Agent': 'linux-radmir-rp/1.0'}), timeout=60) as src:
            if urlsplit(src.url).scheme != 'https':
                raise ValueError('Небезопасное перенаправление')
            with tmp.open('wb') as output:
                shutil.copyfileobj(src, output, 1024 * 1024)
        if not digest_matches(tmp, spec):
            raise ValueError('Не совпала контрольная сумма: ' + dest.name)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest

def download_directories():
    """XDG is parsed as data; never source a user-controlled shell file."""
    roots = []
    config = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'user-dirs.dirs'
    if config.is_file():
        for row in config.read_text().splitlines():
            if row.startswith('XDG_DOWNLOAD_DIR='):
                value = row.split('=', 1)[1].strip().strip('"').replace('${HOME}', str(HOME)).replace('$HOME', str(HOME))
                path = Path(value).expanduser()
                if path.is_absolute():
                    roots.append(path)
    roots += [HOME / 'Downloads', HOME / 'Загрузки']
    return list(dict.fromkeys(roots))

def local_installer(value):
    """An explicit path, a filename in Downloads, or 'auto' selects a local EXE."""
    if str(value) != 'auto':
        path = value.expanduser()
        if path.is_file():
            return path.resolve()
        if path.name == str(path):
            for root in download_directories():
                if (root / path).is_file():
                    return (root / path).resolve()
        raise ValueError('Установщик не найден: ' + str(value))
    found = []
    for root in download_directories():
        if root.is_dir():
            for candidate in root.iterdir():
                if (candidate.is_file() and any(name in candidate.name.lower() for name in ('radmir','rdmr','hassle'))
                        and candidate.suffix.lower() == '.exe'):
                    found.append(candidate)
    if not found:
        raise ValueError('В папках загрузок не найден Radmir EXE; передайте --installer /полный/путь.exe')
    return max(found, key=lambda p: p.stat().st_mtime).resolve()

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(data if isinstance(data, bytes) else data.encode())
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)

class Snapshot:
    """Write-ahead backup; files created during setup are removed on restore."""
    def __init__(self):
        self.root = STATE / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.root.mkdir(parents=True, mode=0o700)
        self.entries = []

    def save(self, path):
        path = path.absolute()
        if any(e['path'] == str(path) for e in self.entries):
            return
        if path.is_symlink():
            raise ValueError('Не заменяем символическую ссылку: ' + str(path))
        copy = self.root / str(len(self.entries))
        existed = path.exists()
        if existed:
            if not path.is_file():
                raise ValueError('Ожидался обычный файл: ' + str(path))
            shutil.copy2(path, copy)
        self.entries.append({'path': str(path), 'backup': copy.name if existed else None})
        atomic(self.root / 'restore.json', json.dumps(self.entries, ensure_ascii=False, indent=2) + '\n')

    def write(self, path, text):
        self.save(path)
        atomic(path, text)

def restore(manifest):
    require_closed()
    manifest = manifest.expanduser().resolve()
    if not manifest.is_relative_to((STATE / 'backups').resolve()) or manifest.name != 'restore.json':
        raise ValueError('Нужен restore.json из каталога резервных копий этого проекта')
    plan = json.loads(manifest.read_text())
    checked = []
    for item in plan:
        dest = Path(item['path'])
        if not dest.is_absolute() or not dest.resolve().is_relative_to(HOME.resolve()) or dest.is_symlink():
            raise ValueError('Недопустимая цель восстановления')
        source = manifest.parent / item['backup'] if item['backup'] else None
        if source and (not source.resolve().is_relative_to(manifest.parent) or not source.is_file()):
            raise ValueError('Резервный файл не найден')
        checked.append((source, dest))
    for source, dest in checked:
        if source:
            atomic(dest, source.read_bytes())
            shutil.copymode(source, dest)
        else:
            dest.unlink(missing_ok=True)
    print('Файлы восстановлены. Игра, Flatpak и системные пакеты не удалены.')

@contextmanager
def operation_lock():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCKFILE.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Установка или запуск Radmir уже выполняется')
        yield

def setup_flatpak():
    call(['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
          'https://dl.flathub.org/repo/flathub.flatpakrepo'])
    if subprocess.run(['flatpak', 'info', APP], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        call(['flatpak', 'install', '--user', '-y', 'flathub', APP])

def ensure_runner():
    runner = DATA / 'runners' / DOWNLOADS['proton']['directory']
    if (runner / 'proton').is_file():
        return runner
    if runner.exists():
        raise ValueError('Неполный каталог Proton, проверьте его: ' + str(runner))
    archive = fetch(DOWNLOADS['proton'], CACHE / 'GE-Proton11-11-x86_64.tar.gz')
    runner.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='extract-', dir=runner.parent) as tmp:
        with tarfile.open(archive) as tf:
            if not hasattr(tarfile, 'data_filter'):
                raise ValueError('Обновите Python: необходим безопасный tarfile.data_filter (3.12+ или исправленный 3.10/3.11)')
            tf.extractall(tmp, filter='data')
        candidates = list(Path(tmp).glob('*/proton'))
        if len(candidates) != 1:
            raise ValueError('Неожиданная структура архива Proton')
        shutil.move(str(candidates[0].parent), runner)
    return runner

def command(prefix, runner, exe, logs, extra=()):
    umu = DATA / 'umu-run'
    args = ['flatpak', 'run', '--command=env', '--filesystem=' + str(DATA),
            '--filesystem=' + str(prefix), '--filesystem=' + str(logs)]
    if CACHE.is_dir():
        args.append('--filesystem=' + str(CACHE) + ':ro')
    if isinstance(exe, Path):
        args.append('--filesystem=' + str(exe.parent) + ':ro')
    args += [APP]
    for key in ['WINEDLLOVERRIDES', 'PROTON_ENABLE_WAYLAND', 'PROTON_USE_WINED3D',
                'PROTON_USE_WOW64', 'PROTON_HEAP_DELAY_FREE', 'PROTON_FORCE_LARGE_ADDRESS_AWARE', 'STEAM_COMPAT_CONFIG', 'MANGOHUD', 'VK_ADD_IMPLICIT_LAYER_PATH']:
        args += ['-u', key]
    args += ['WINEPREFIX=' + str(prefix), 'PROTONPATH=' + str(runner), 'GAMEID=0',
             'UMU_USE_STEAM=1', 'UMU_CONTAINER_NSENTER=1', 'PROTON_USE_WOW64=0', 'MANGOHUD=0',
             'WINEDEBUG=-all,err+all', str(umu), str(exe)]
    return args + list(extra)

def font_plan(windows=None):
    # Use the pinned CBDT font across distros (Fedora's packaged font is COLRv1).
    emoji = fetch(DOWNLOADS['emoji'], CACHE / 'NotoColorEmoji.ttf')
    matches = call(['fc-match', '-f', '%{file}', 'DejaVu Sans'], capture_output=True, text=True).stdout
    dejavu = Path(matches)
    if not dejavu.is_file() or dejavu.name.lower() != 'dejavusans.ttf':
        raise ValueError('Не найден DejaVuSans.ttf; установите пакет DejaVu для вашего дистрибутива')
    result = [(emoji, 'NotoColorEmoji.ttf', 'Noto Color Emoji (TrueType)'),
              (dejavu, 'DejaVuSans.ttf', 'DejaVu Sans (TrueType)')]
    if windows:
        wanted = {'segoeui.ttf': 'Segoe UI (TrueType)', 'seguisb.ttf': 'Segoe UI Semibold (TrueType)',
                  'seguiemj.ttf': 'Segoe UI Emoji (TrueType)', 'segoeuiemoji.ttf': 'Segoe UI Emoji (TrueType)'}
        imported = set()
        for f in sorted(windows.expanduser().iterdir()):
            key = f.name.lower()
            if f.is_file() and key in wanted and wanted[key] not in imported:
                name = 'seguiemj.ttf' if key == 'segoeuiemoji.ttf' else key
                with f.open('rb') as font_file:
                    signature = font_file.read(4)
                if signature not in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf'):
                    raise ValueError('Некорректный файл шрифта: ' + str(f))
                result.append((f, name, wanted[key])); imported.add(wanted[key])
        if not imported:
            raise ValueError('В папке нет Segoe UI / Semibold / Emoji; см. docs/fonts.md')
    return result

def install_fonts(prefix, runner, logs, snapshot, windows=None):
    fonts = font_plan(windows)
    # Back up registry before invoking Wine, which changes registry files as a whole.
    for name in ['user.reg', 'system.reg', 'userdef.reg']:
        snapshot.save(prefix / name)
    for source, name, family in fonts:
        target = prefix / 'drive_c/windows/Fonts' / name
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            snapshot.write(target, source.read_bytes())
        for hive in ['HKLM', 'HKCU']:
            for key in FONT_KEYS:
                run_logged(command(prefix, runner, 'reg.exe', logs,
                           ['add', hive + '\\' + key, '/v', family, '/t', 'REG_SZ', '/d', name, '/f']),
                           logs / ('font-' + name + '-' + hive + '-' + str(FONT_KEYS.index(key)) + '.log'))
    # Add fallback family mappings only when original Segoe wasn't supplied.
    families = {family for _, _, family in fonts}
    for missing, fallback in [('Segoe UI', 'DejaVu Sans'), ('Segoe UI Semibold', 'DejaVu Sans'),
                              ('Segoe UI Emoji', 'Noto Color Emoji')]:
        key = r'HKCU\Software\Wine\Fonts\Replacements'
        query = subprocess.run(command(prefix, runner, 'reg.exe', logs,
                               ['query', key, '/v', missing]), capture_output=True, text=True, errors='replace')
        import re
        own = bool(re.search(r'REG_MULTI_SZ\s+' + re.escape(fallback) + r'\s*$', query.stdout, re.M))
        if missing + ' (TrueType)' in families:
            if own:
                run_logged(command(prefix, runner, 'reg.exe', logs, ['delete', key, '/v', missing, '/f']),
                           logs / ('remove-fallback-' + missing.replace(' ', '-') + '.log'))
        elif query.returncode != 0 or own:
            run_logged(command(prefix, runner, 'reg.exe', logs,
                       ['add', key, '/v', missing, '/t', 'REG_MULTI_SZ', '/d', fallback, '/f']),
                       logs / ('fallback-' + missing.replace(' ', '-') + '.log'))
    # Host + sandboxed CEF fallback use fontconfig. Preserve existing user rules.
    host_fonts = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'fonts/linux-radmir-rp'
    for source, name, _ in fonts:
        snapshot.write(host_fonts / name, source.read_bytes())
    call(['fc-cache', '-f', str(host_fonts)])

def register(exe, prefix, runner, snapshot):
    target = FAUGUS / 'games.json'
    original = target.read_bytes() if target.exists() else b'[]'
    games = json.loads(original)
    if not isinstance(games, list) or any(not isinstance(g, dict) for g in games):
        raise ValueError('Неожиданный формат списка игр Faugus')
    matching = [g for g in games if g.get('gameid') == GAMEID]
    if len(matching) > 1:
        raise ValueError('Дубликаты Radmir в Faugus')
    if matching:
        record = matching[0]
        old = Path(record.get('prefix', '')).expanduser()
        if old != prefix:
            raise ValueError('Radmir в Faugus уже использует другой префикс. Укажите --prefix ' + shlex.quote(str(old)))
    else:
        record = {'gameid': GAMEID, 'title': 'Radmir CRMP', 'game_arguments': '',
                  'launch_arguments': '', 'playtime': 0, 'hidden': False, 'runtime': 'umu-steamrt4'}
        games.append(record)
    record.update(path=str(exe), prefix=str(prefix), runner=str(runner))
    import re
    launch_args = re.sub(r'(?<!\S)PROTON_USE_WOW64=(?:[^\s]+)\s*', '', record.get('launch_arguments', ''))
    record['launch_arguments'] = (launch_args.strip() + ' PROTON_USE_WOW64=0').strip()
    for key in ['mangohud', 'gamemode', 'sdl_enabled', 'no_sleep', 'disable_umu', 'discord_rpc']:
        record.setdefault(key, '')
    if target.exists() and target.read_bytes() != original:
        raise ValueError('Faugus изменил games.json. Закройте его и повторите.')
    snapshot.write(target, json.dumps(games, ensure_ascii=False, indent=2) + '\n')
    # Also supply UMU where Faugus itself expects it; never replace an existing copy.
    if not (FAUGUS / 'umu-run').exists():
        snapshot.write(FAUGUS / 'umu-run', (DATA / 'umu-run').read_bytes())
        (FAUGUS / 'umu-run').chmod(0o755)

def install_hud():
    import re
    runtime = call(['flatpak', 'info', '--show-runtime', APP], capture_output=True, text=True).stdout.strip()
    location = call(['flatpak', 'info', '--show-location', runtime], capture_output=True, text=True).stdout.strip()
    text = (Path(location) / 'metadata').read_text()
    section = re.search(r'\[Extension org\.freedesktop\.Platform\.VulkanLayer\]\n([^\[]*)', text)
    version = re.search(r'^version\s*=\s*(\S+)', section[1], re.M) if section else None
    if not version:
        raise ValueError('В runtime не найдена ветка MangoHud')
    ref = 'org.freedesktop.Platform.VulkanLayer.MangoHud//' + version[1]
    if subprocess.run(['flatpak', 'info', ref], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        call(['flatpak', 'install', '--user', '-y', 'flathub', ref])
    import hud_tools
    hud_tools.configure_hud(GAMEID)


def require_closed():
    from display import require_closed as prefix_closed
    prefix_closed()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            name=(proc/'comm').read_text().strip().lower()
        except OSError:
            continue
        if 'faugus' in name:
            raise ValueError('Закройте Faugus перед настройкой его записей')


def run_logged(args, logfile):
    print('Журнал: ' + str(logfile), flush=True)
    with logfile.open('w') as out:
        call(args, stdout=out, stderr=subprocess.STDOUT)
