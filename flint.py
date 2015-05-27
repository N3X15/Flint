'''
Flint - Firefox Addon Installer

Copyright (c) 2015 Rob "N3X15" Nelson <nexisentertainment@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
'''

import os
import sys
import argparse
import yaml
import configparser
import tempfile
import untangle
import pickle
import hashlib

from mozprofile import Profile
from mozprofile.addons import AddonManager
from mozprofile.prefs import Preferences

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, 'lib', 'buildtools'))
sys.path.append(os.path.join(script_dir, 'lib', 'amo-api', 'python'))  # Packaging nightmare.

from buildtools import cmd, log, http
from buildtools import os_utils
from buildtools.wrapper import Git
from buildtools.bt_logging import IndentLogger

from amo.api import Server

global FF_APPDATA_DIR, FF_PROFILE_DIR, FF_PROFILE_INI, PACKAGES

FLINT_VERSION = '0.0.1'

flint_temp = os.path.join(os.getcwd(), 'packages')
flint_cachefile = os.path.join(flint_temp, '_cache.dat')
home_dir = os.path.expanduser('~')


def _getMozAddonURI(addonID):
  return 'https://addons.mozilla.org/firefox/downloads/latest/{0}/addon-{0}-latest.xpi?src=flint'.format(addonID)


class APICache:
  data = {}

  @classmethod
  def Store(cls, key, value):
    cls.data[key] = value

    with open(flint_cachefile, 'w') as f:
      pickle.dump(cls.data, f)

  @classmethod
  def Load(cls):
    if os.path.isfile(flint_cachefile):
      with open(flint_cachefile, 'r') as f:
        cls.data = pickle.load(f)

  @classmethod
  def Get(cls, key):
    return cls.data.get(key, None)


class FFPackage(object):

  def __init__(self, _id, name='', url='', filename=None, config={}):
    self.id = _id
    self.name = name
    self.url = url
    self.filename = filename if filename else self.id + '.xpi'
    self.config = config

  def _grabURL(self, yml, dev):
    prefix = 'dev-' if dev else ''
    if prefix + 'url' in yml:
      self.url = yml['url']
      return True
    if dev:
      return self._grabURL(yml, False)
    return False

  def fromYaml(self, yml, args):
    self.name = yml['name']
    self.url = ''
    if not self._grabURL(yml, args.dev):
      raise Exception('url or moz-addon must be specified for package {}.'.format(self.id))
    self.filename = yml['filename'] if 'filename' in yml else self.id + '.xpi'
    self.config = yml.get('config', {})

  def install(self, fp, args, prefs):
    fullpath = os.path.join(flint_temp, self.filename)
    with log.info('Installing %s:', self.name):
      if not os.path.isfile(fullpath):
        if args.dry_run:
          log.info('Would download %s from %s.', self.filename, self.url)
        else:
          with log.info('Downloading %s...', self.filename):
            http.DownloadFile(self.url, fullpath)
      if args.dry_run or args.dl_only:
        log.info('Would install %s.', self.filename)
      else:
        with log.info('Installing %s...', self.filename):
          fp.addon_manager.install_from_path(fullpath)

      if len(self.config) > 0:
        with log.info('Configuring...'):
          for k, v in self.config.items():
            if args.dry_run:
              log.info('Would set %s to %r', k, v)
            else:
              prefs[k] = v
              log.info('Set %s to %r', k, str(v))


class AMOPackage(FFPackage):
  api = Server('amo')

  def __init__(self, _id, name='', amoID=0, filename=None, config={}):
    super(AMOPackage, self).__init__(_id, name, None, filename, config)
    self.amoID = amoID

  def _grabURL(self, yml, dev):
    self.amoID = yml['moz-addon']
    self.devmode = dev
    return True

  def fromYaml(self, yml, args):
    FFPackage.fromYaml(self, yml, args)

  def _grabRealURL(self, addon=None):
    if not addon:
      apic_key = 'amo_' + str(self.amoID)
      xml = APICache.Get(apic_key)
      if xml is None:
        xml = self.api.addon.get(id=self.amoID)
        APICache.Store(apic_key, xml)
      addon = untangle.parse(xml)
    for install in addon.addon.get_elements('install'):
      if self.devmode:
        if install.get_attribute('status') == 'Beta':
          log.info('Found BETA URL: %s', install.cdata)
          return install['hash'], install.cdata
      else:
        if not install.get_attribute('status'):
          log.info('Found STABLE URL: %s', install.cdata)
          log.info(install)
          return install['hash'], install.cdata
    if self.devmode:
      self.devmode = False
      return self._grabRealURL(addon)
    return False

  def get_hash_of(self, algo_cb, filename, blocksize=2048):
    m = algo_cb()
    with open(filename, 'rb') as f:
      while True:
        b = f.read(blocksize)
        if not b:
          break
        m.update(b)
    return m.hexdigest().lower()

  def check_hash_of(self, _hash, filename):
    hashtype, hashvalue = _hash.split(':')
    return self.get_hash_of(getattr(hashlib, hashtype), filename) == hashvalue.lower()

  def install(self, fp, args, prefs):
    self.hash, self.url = self._grabRealURL()
    fullpath = os.path.join(flint_temp, self.filename)
    if os.path.isfile(fullpath) and not self.check_hash_of(self.hash, fullpath):
      os.remove(fullpath)
      log.warn('Hash mismatch: %s', fullpath)
    FFPackage.install(self, fp, args, prefs)

PACKAGES = {}

FF_APPDATA_DIR = ''
FF_PROFILE_DIR = ''
FF_PROFILE_INI = ''


def locateFirefoxDirs():
  global FF_APPDATA_DIR, FF_PROFILE_DIR, FF_PROFILE_INI, PACKAGES
  if sys.platform == 'win32':
    FF_APPDATA_DIR = os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox')
  else:
    FF_APPDATA_DIR = os.path.join(home_dir, '.mozilla', 'firefox')
  log.info('AppData: %s', FF_APPDATA_DIR)
  FF_PROFILE_INI = os.path.join(FF_APPDATA_DIR, 'profiles.ini')

  ini = configparser.ConfigParser()

  os_utils.ensureDirExists(FF_APPDATA_DIR, mode=0o700, noisy=True)

  if not os.path.isfile(FF_PROFILE_INI):
    ini.add_section('General')
    ini.set('General', 'StartWithLastProfile', '1')

    ini.add_section('Profile0')
    ini.set('Profile0', 'Name', 'default')
    ini.set('Profile0', 'IsRelative', '1')
    ini.set('Profile0', 'Path', 'Profiles/generated.default')
    ini.set('Profile0', 'Default', '1')
    with open(FF_PROFILE_INI, 'w') as f:
      ini.write(f)
  else:
    ini.read(FF_PROFILE_INI)
  FF_PROFILE_DIR = None
  for section in ini.sections():
    if ini.has_option(section, 'Default'):
      FF_PROFILE_DIR = ini.get(section, 'Path')
      if ini.getboolean(section, 'IsRelative'):
        FF_PROFILE_DIR = os.path.join(FF_APPDATA_DIR, FF_PROFILE_DIR)
  if not FF_PROFILE_DIR:
    raise Exception('Unable to find FF_PROFILE_DIR.')
  log.info('Profile: %s', FF_PROFILE_DIR)


if __name__ == '__main__':
  argp = argparse.ArgumentParser(prog='tome', description='Install and configure Firefox addons.', version=FLINT_VERSION)
  argp.add_argument('configfile', type=argparse.FileType('r'), help='YAML configuration file.')
  argp.add_argument('--dry-run', dest='dry_run', action='store_true', default=False, help='Do not install addons, just go through the motions.')
  argp.add_argument('--dl-only', dest='dl_only', action='store_true', default=False, help='Do not install addons, only download them.  Good for precaching for an offline install.')
  argp.add_argument('--dev', dest='dev', action='store_true', default=False, help='Select the development build of addons, if available.')
  argp.add_argument('-R', '--refresh', dest='refresh', action='store_true', default=False, help='Re-download addons.')

  args = argp.parse_args()

  if args.dry_run:
    log.info('DRY-RUN ENABLED.')

  if args.refresh:
    log.info('Refreshing cache...')
    if os.path.isdir(flint_temp):
      os_utils.safe_rmtree(flint_temp)

  os_utils.ensureDirExists(flint_temp, mode=0o700, noisy=True)

  APICache.Load()

  locateFirefoxDirs()

  cfg = {}
  with log.info('Loading %s...', args.configfile.name):
    cfg = yaml.load(args.configfile)

  PACKAGES = {}
  with log.info('Loading packages...'):
    with open('.packages.yml', 'r') as f:
      for pkgID, pkgSpec in yaml.load(f).items():
        PACKAGES[pkgID] = pkgSpec
        if 'aliases' in pkgSpec:
          cleanSpec = pkgSpec.copy()
          del cleanSpec['aliases']
          for alias in pkgSpec['aliases']:
            PACKAGES[alias] = cleanSpec
          PACKAGES[pkgID] = cleanSpec

  prefsjs_path = os.path.join(FF_PROFILE_DIR, 'prefs.js')
  prefs = {k: v for k, v in reversed(Preferences.read_prefs(prefsjs_path))}
  with log.info('Installing addons...'):
    pkgs = []
    for aspec in cfg.get('addons', {}):
      yml = None
      if isinstance(aspec, (str, unicode)):
        yml = PACKAGES[aspec]
        yml['id'] = aspec
      if isinstance(aspec, dict):
        yml = aspec
      if yml:
        if 'id' not in yml:
          print(repr(yml))
        if 'moz-addon' in yml:
          pkg = AMOPackage(yml['id'])
        else:
          pkg = FFPackage(yml['id'])
        pkg.fromYaml(yml, args)
        pkgs.append(pkg)
    fp = Profile(FF_PROFILE_DIR, restore=False)
    for pkg in pkgs:
      pkg.install(fp, args, prefs)

  with log.info('Setting preferences...'):
    changed = False
    for k, v in cfg.get('prefs', {}).items():
      if k not in prefs or prefs[k] != cfg['prefs'][k]:
        prefs[k] = cfg['prefs'][k]
        log.info('%s = %s', k, v)
        changed = True
    if changed:
      prefs_sorted = []
      for k in sorted(prefs.keys()):
        prefs_sorted.append((k, prefs[k]))
      with open(prefsjs_path, 'w') as pf:
        Preferences.write(pf, prefs_sorted)
      log.info('Wrote prefs.js.')
