"""Пути, параметры префикса и команда запуска Radmir через Flatpak/UMU."""
import json
import os
from pathlib import Path
import subprocess
import common

DEFAULT_PREFIX = common.HOME / 'Games/radmir-crmp/prefix'
PROFILE = common.DATA / 'profile.json'
PREFIX = DEFAULT_PREFIX
RUNNER = common.DATA / 'runners' / common.DOWNLOADS['proton']['directory']
STATE = common.STATE


def configure(prefix=None):
    global PREFIX
    if prefix is None and PROFILE.is_file():
        saved = json.loads(PROFILE.read_text())
        if not isinstance(saved, dict) or not isinstance(saved.get('prefix'), str):
            raise ValueError('Некорректный profile.json: нужен строковый prefix')
        prefix = Path(saved['prefix'])
    raw = Path(prefix or DEFAULT_PREFIX).expanduser()
    if raw.is_symlink():
        raise ValueError('Префикс не должен быть символической ссылкой')
    value = raw.resolve()
    if not value.is_relative_to(common.HOME.resolve()) or value == common.HOME.resolve():
        raise ValueError('Выберите отдельную папку префикса внутри домашнего каталога')
    PREFIX = value
    return PREFIX


def launcher():
    exe = PREFIX / 'drive_c/Program Files (x86)/RADMIR Games/Launcher/RADMIR Launcher.exe'
    if exe.is_file() and not exe.resolve().is_relative_to(PREFIX.resolve()):
        raise ValueError('Лаунчер должен находиться внутри выбранного префикса')
    return exe


def command(exe, logs, extra=(), hud=True):
    args = common.command(PREFIX, RUNNER, exe, logs, extra)
    folder = common.DATA / common.GAMEID
    required = [folder / 'MangoHud.conf', folder / 'presets.conf', folder / 'layers']
    if hud and all(p.exists() for p in required):
        before = args.index(common.APP)
        args.insert(before, '--filesystem=' + str(folder) + ':ro')
        args = ['MANGOHUD=1' if x == 'MANGOHUD=0' else x for x in args]
        idx = args.index(str(common.DATA / 'umu-run'))
        args[idx:idx] = ['DXVK_HUD=0', 'MANGOHUD_CONFIGFILE=' + str(folder/'MangoHud.conf'),
                         'MANGOHUD_PRESETSFILE=' + str(folder/'presets.conf'),
                         'VK_ADD_IMPLICIT_LAYER_PATH=' + str(folder/'layers')]
    return args


def run(exe, logs, extra=()):
    target = logs / 'launcher.log'
    print('Запуск официального лаунчера Radmir. Журнал: ' + str(target), flush=True)
    with target.open('w') as output:
        with subprocess.Popen(command(exe, logs, extra), cwd=exe.parent, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors='replace') as process:
            for line in process.stdout:
                output.write(line)
                output.flush()
                print(line, end='', flush=True)
            return process.wait()
