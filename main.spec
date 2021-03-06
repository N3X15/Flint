# -*- mode: python -*-
script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, 'lib', 'buildtools'))
a = Analysis(['flint.py'],
             pathex=['lib/buildtools','lib/amo-api/python'],
             hiddenimports=['buildtools','amo.api'],
             hookspath=None)
#files = os.listdir('icons')
#for file in files:
#    a.datas += [('icons' + os.sep + file, 'icons' + os.sep + file, 'DATA')]

pyz = PYZ(a.pure)

ename=os.path.join('bin', 'flint')
if sys.platform.startswith('win') or sys.platform.startswith('microsoft'):
    ename += '.exe'

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=ename,
          debug=False,
          strip=None,
          upx=True,
          console=True,
          #icon=...
)
#app = BUNDLE(exe, name='Flint.app')
