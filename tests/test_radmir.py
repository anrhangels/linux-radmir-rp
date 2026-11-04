import base64
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import audio
import audio_proxy
import common
import display
import install
import play
import settings


class FeedTests(unittest.TestCase):
    base='https://dl.hasslecdn.com/launcher/hassle/'
    digest=base64.b64encode(hashlib.sha512(b'MZfixture').digest()).decode()
    def feed(self,path='RADMIR Launcher Setup.exe'):
        return 'version: 999\npath: '+path+'\nsha512: '+self.digest+'\n'

    def test_current_feed_checks_hash_and_encodes_spaces(self):
        spec=install.parse_feed(self.feed(),self.base)
        self.assertEqual(spec['url'],self.base+'RADMIR%20Launcher%20Setup.exe')
        self.assertEqual(spec['sha512'],hashlib.sha512(b'MZfixture').hexdigest())

    def test_feed_rejects_changed_hosts_and_traversal(self):
        for path in ['https://evil.example/setup.exe','../outside.exe','//evil.example/a.exe','https://user:pass@dl.hasslecdn.com/launcher/hassle/a.exe']:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):install.parse_feed(self.feed(path),self.base)

    def test_feed_rejects_missing_or_invalid_digest(self):
        for feed in ['path: a.exe\n', self.feed().replace(self.digest,'!bad!'),self.feed().replace(self.digest,base64.b64encode(b'short').decode())]:
            with self.assertRaises(ValueError):install.parse_feed(feed,self.base)

    def test_download_uses_published_sha512_and_fixed_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);response=io.BytesIO(self.feed().encode());response.url=self.base+'latest.yml'
            captured=[]
            def fetch(spec,path):captured.append(spec);path.parent.mkdir(parents=True);path.write_bytes(b'MZfixture');return path
            with patch.object(install,'urlopen',return_value=response),patch.object(common,'CACHE',root/'cache'),patch.object(common,'fetch',side_effect=fetch):
                exe=install.download_launcher(root)
            self.assertEqual(captured[0]['sha512'],hashlib.sha512(b'MZfixture').hexdigest())
            self.assertEqual(exe.name,'RADMIRLauncherSetup.exe')

    def test_pe_validation_rejects_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'file.exe';file.write_bytes(b'<html>')
            with self.assertRaises(ValueError):install.validate_exe(file)

    def test_native_ready_requires_both_architectures_and_native_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(settings,'PREFIX',root):
                self.assertFalse(install.native_ready())
                for directory in ['system32','syswow64']:
                    for name in install.DLLS:
                        p=root/'drive_c/windows'/directory/(name+'.dll');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'MZfixture native')
                self.assertTrue(install.native_ready())
                (root/'drive_c/windows/system32/ucrtbase.dll').write_bytes(b'MZ Wine builtin DLL')
                self.assertFalse(install.native_ready())


class MusicTests(unittest.TestCase):
    def test_cp1251_utf8_and_unicode_paths_have_same_target(self):
        path='Музыка/Песня.mp3'
        cp=''.join('%%%02X'%b for b in path.encode('cp1251'))
        utf=''.join('%%%02X'%b for b in path.encode('utf8'))
        expected=audio_proxy.normalized('http://music.radmir.online/'+path)
        self.assertEqual(audio_proxy.normalized('http://music.radmir.online/'+cp),expected)
        self.assertEqual(audio_proxy.normalized('http://music.radmir.online/'+utf),expected)
        self.assertEqual(audio_proxy.normalized('http://music.radmir.online/'+path.encode('cp1251').decode('latin1')),expected)

    def test_normalization_is_limited_to_music_host_and_http(self):
        for url in ['https://music.radmir.online/a','http://elsewhere/a','http://music.radmir.online:81/a','http://u:p@music.radmir.online/a']:
            with self.assertRaises(ValueError):audio_proxy.normalized(url)

    def test_query_preserved_and_fragment_removed(self):
        result=audio_proxy.normalized('http://music.radmir.online/a.mp3?key=value#ignore')
        self.assertEqual(result,'http://music.radmir.online/a.mp3?key=value')

    def test_registry_snapshot_ignores_other_sections_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);section=audio.KEY.replace('\\','\\\\')
            (root/'user.reg').write_text('['+section+'] 100\n"ProxyEnable"=dword:00000000\n"ProxyServer"="old:80"\n"Unrelated"="keep"\n[Other]\n"ProxyServer"="wrong"\n')
            with patch.object(settings,'PREFIX',root):self.assertEqual(audio.snapshot(),{'ProxyEnable':'dword:00000000','ProxyServer':'"old:80"'})

    def test_proxy_binds_loopback_and_restores_after_game_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'restore.json';server=Mock(server_address=('127.0.0.1',12000));worker=Mock();calls=[]
            with patch.object(audio,'ThreadingHTTPServer',return_value=server) as factory,patch.object(audio.threading,'Thread',return_value=worker),patch.object(audio,'snapshot',return_value={'ProxyEnable':'dword:00000000'}),patch.object(audio,'registry',side_effect=lambda v,l,n:calls.append((v,n))),patch.object(settings,'PREFIX',root):
                with self.assertRaisesRegex(RuntimeError,'game stopped'):
                    with audio.session(marker,root):
                        self.assertTrue(marker.exists());raise RuntimeError('game stopped')
            self.assertEqual(factory.call_args.args[0],('127.0.0.1',0))
            self.assertEqual(calls[-1],({'ProxyEnable':'dword:00000000'},'restore-proxy'))
            self.assertFalse(marker.exists());server.shutdown.assert_called_once();server.server_close.assert_called_once()

    def test_failed_restore_keeps_recovery_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'marker';server=Mock(server_address=('127.0.0.1',12000))
            def registry(values,logs,label):
                if label=='restore-proxy':raise ValueError('restore failed')
            with patch.object(audio,'ThreadingHTTPServer',return_value=server),patch.object(audio.threading,'Thread'),patch.object(audio,'snapshot',return_value={}),patch.object(audio,'registry',side_effect=registry),patch.object(settings,'PREFIX',root):
                with self.assertRaisesRegex(ValueError,'restore failed'):
                    with audio.session(marker,root):pass
            self.assertTrue(marker.exists());server.server_close.assert_called_once()

    def test_recovery_rejects_different_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'marker';marker.write_text(json.dumps({'prefix':'/other','values':{}}))
            with patch.object(settings,'PREFIX',root),patch.object(audio,'registry') as registry:
                with self.assertRaises(ValueError):audio.recover(marker,root)
                registry.assert_not_called()


class ScreenTests(unittest.TestCase):
    screens='DP-1 connected primary 2560x1600+0+0\nHDMI-2 connected 1920x1080-1920+0\nVIRTUAL disconnected\n'
    def test_choose_uses_real_fullhd_without_fixed_port_names(self):
        data=display.outputs(self.screens)
        self.assertEqual(display.choose(data),'HDMI-2')
        self.assertIsNone(display.choose({'eDP-1':{'primary':True,'size':(2560,1600)}}))

    def test_primary_fullhd_is_kept(self):
        self.assertEqual(display.choose({'first':{'primary':False,'size':(1920,1080)},'second':{'primary':True,'size':(1920,1080)}}),'second')

    def test_primary_restored_on_launch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'marker';after=self.screens.replace('connected primary 2560','connected 2560').replace('connected 1920','connected primary 1920');calls=[]
            with patch.dict(os.environ,{'DISPLAY':':test'}),patch.object(display.shutil,'which',return_value='/bin/xrandr'),patch.object(display,'query',side_effect=[self.screens,after,after]),patch.object(common,'call',side_effect=lambda a,**kw:calls.append(a)):
                with self.assertRaises(RuntimeError):
                    with display.temporary_fullhd(marker,root):raise RuntimeError('game failed')
            self.assertEqual(calls[0],['xrandr','--output','HDMI-2','--primary'])
            self.assertEqual(calls[-1],['xrandr','--output','DP-1','--primary'])
            self.assertFalse(marker.exists());self.assertFalse(any('--mode' in c for c in calls))

    def test_recovery_respects_manually_changed_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'marker';marker.write_text(json.dumps({'selected':'HDMI-2','previous':'DP-1'}))
            with patch.object(display,'query',return_value=self.screens),patch.object(common,'call') as call:
                display.recover(marker);call.assert_not_called()
            self.assertFalse(marker.exists())


class SetupIntegrationTests(unittest.TestCase):
    def test_install_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(common,'HOME',root),patch.object(common,'urlopen',side_effect=AssertionError('network')),patch.object(settings,'PROFILE',root/'profile'),patch.object(settings,'PREFIX',root/'prefix'),patch.object(sys,'argv',['install.py','--plan','--prefix',str(root/'prefix')]):
                self.assertEqual(install.main(),0)
            self.assertEqual(list(root.iterdir()),[])

    def test_wow64_off_and_hud_disable_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ['MangoHud.conf','presets.conf','layers']:
                p=root/common.GAMEID/name;p.parent.mkdir(parents=True,exist_ok=True)
                p.mkdir() if name=='layers' else p.write_text('fixture')
            with patch.object(common,'DATA',root),patch.object(settings,'PREFIX',root/'prefix'),patch.object(settings,'RUNNER',root/'runner'):
                no_hud=settings.command('reg.exe',root,hud=False)
                with_hud=settings.command('reg.exe',root,hud=True)
            self.assertIn('PROTON_USE_WOW64=0',no_hud);self.assertIn('MANGOHUD=0',no_hud)
            self.assertIn('MANGOHUD=1',with_hud);self.assertEqual(no_hud[-1],'reg.exe')

    def test_one_lock_covers_recovery_and_full_game_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);events=[]
            @contextmanager
            def lock():
                events.append('lock');yield;events.append('unlock')
            @contextmanager
            def audio_session(*args,**kw):
                events.append('audio-enter');yield;events.append('audio-exit')
            @contextmanager
            def screen_session(*args,**kw):
                events.append('screen-enter');yield;events.append('screen-exit')
            with patch.object(sys,'argv',['radmir']),patch.object(play.os,'getuid',return_value=1000),patch.object(settings,'configure'),patch.object(play,'check',return_value=0),patch.object(display,'require_closed'),patch.object(common,'STATE',root),patch.object(common,'operation_lock',side_effect=lock),patch.object(audio,'recover',side_effect=lambda *a:events.append('audio-recover')),patch.object(display,'recover',side_effect=lambda *a:events.append('screen-recover')),patch.object(audio,'session',side_effect=audio_session),patch.object(display,'temporary_fullhd',side_effect=screen_session),patch.object(settings,'run',side_effect=lambda *a:events.append('game') or 0):
                self.assertEqual(play.main(),0)
            self.assertEqual(events,['lock','audio-recover','screen-recover','audio-enter','screen-enter','game','screen-exit','audio-exit','unlock'])

    def test_install_existing_prefix_keeps_other_games_and_installs_runtime_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prefix=root/'prefix';data=root/'data';state=root/'state';runner=data/'runner';runner.mkdir(parents=True);(runner/'proton').write_text('fixture')
            faugus=root/'faugus';faugus.mkdir();other={'gameid':'unrelated','path':'other.exe','launch_arguments':'KEEP=1'};(faugus/'games.json').write_text(json.dumps([other]))
            exe=prefix/'drive_c/Program Files (x86)/RADMIR Games/Launcher/RADMIR Launcher.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'MZfixture')
            def fetch(spec,path):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'umu');return path
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(root/'share')}),patch.object(common,'HOME',root),patch.object(common,'DATA',data),patch.object(common,'STATE',state),patch.object(common,'FAUGUS',faugus),patch.object(common,'LOCKFILE',state/'lock'),patch.object(settings,'PROFILE',data/'profile.json'),patch.object(settings,'PREFIX',prefix),patch.object(settings,'RUNNER',runner),patch.object(common,'require_closed'),patch.object(common,'setup_flatpak'),patch.object(common,'ensure_runner',return_value=runner),patch.object(common,'fetch',side_effect=fetch),patch.object(common,'install_fonts'),patch.object(install,'native_ready',return_value=True),patch.object(install,'download_launcher',side_effect=AssertionError('launcher already exists')),patch.object(install.shutil,'which',return_value='/bin/fixture'),patch.object(sys,'argv',['install.py','--prefix',str(prefix),'--no-hud']):
                self.assertEqual(install.main(),0)
            games=json.loads((faugus/'games.json').read_text());self.assertEqual(games[0],other)
            self.assertEqual(games[1]['gameid'],'radmir-crmp');self.assertIn('PROTON_USE_WOW64=0',games[1]['launch_arguments'])
            self.assertTrue((root/'.local/bin/radmir').exists())
            self.assertTrue((data/'tools/scripts/play.py').exists())
            self.assertEqual(json.loads((data/'profile.json').read_text())['prefix'],str(prefix))

    def test_clean_install_runs_graphics_setup_before_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prefix=root/'prefix';data=root/'data';state=root/'state';runner=data/'runner';runner.mkdir(parents=True);(runner/'proton').write_text('fixture')
            faugus=root/'faugus';package=root/'setup.exe';package.write_bytes(b'MZfixture');events=[]
            exe=prefix/'drive_c/Program Files (x86)/RADMIR Games/Launcher/RADMIR Launcher.exe'
            def fetch(spec,path):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'umu');return path
            def logged(args,path):
                if 'winetricks' in args:
                    self.assertIn('ucrtbase2019',args);self.assertIn('d3dcompiler_47',args);events.append('libraries')
                else:
                    self.assertIn('/S',args);events.append('launcher');exe.parent.mkdir(parents=True);exe.write_bytes(b'MZfixture')
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(root/'share')}),patch.object(common,'HOME',root),patch.object(common,'DATA',data),patch.object(common,'STATE',state),patch.object(common,'FAUGUS',faugus),patch.object(common,'LOCKFILE',state/'lock'),patch.object(settings,'PROFILE',data/'profile.json'),patch.object(settings,'PREFIX',prefix),patch.object(settings,'RUNNER',runner),patch.object(common,'require_closed'),patch.object(common,'setup_flatpak'),patch.object(common,'ensure_runner',return_value=runner),patch.object(common,'fetch',side_effect=fetch),patch.object(common,'install_fonts'),patch.object(common,'run_logged',side_effect=logged),patch.object(install,'native_ready',side_effect=[False,True]),patch.object(install,'download_launcher',return_value=package),patch.object(install.shutil,'which',return_value='/bin/fixture'),patch.object(sys,'argv',['install.py','--prefix',str(prefix),'--no-hud']):
                self.assertEqual(install.main(),0)
            self.assertEqual(events,['libraries','launcher'])
            self.assertTrue((prefix/'.linux-radmir-rp-managed').is_file())
            plans=list((state/'backups').glob('*/restore.json'));self.assertEqual(len(plans),1)
            self.assertTrue(any(e['path'].endswith('system32/ucrtbase.dll') for e in json.loads(plans[0].read_text())))

    def test_busy_lock_stops_parallel_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(common,'STATE',root),patch.object(common,'LOCKFILE',root/'lock'):
                with common.operation_lock():
                    with self.assertRaises(ValueError):
                        with common.operation_lock():pass


if __name__=='__main__':unittest.main()
