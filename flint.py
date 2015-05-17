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

from mozprofile import Profile
from mozprofile.addons import AddonManager
from mozprofile.prefs import Preferences

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, 'lib', 'buildtools'))

from buildtools import cmd, log, http
from buildtools import os_utils
from buildtools.wrapper import Git
from buildtools.bt_logging import IndentLogger

global FF_APPDATA_DIR, FF_PROFILE_DIR, FF_PROFILE_INI, PACKAGES

FLINT_VERSION = '0.0.1'

flint_temp = os.path.join(os.getcwd(), 'packages')
home_dir = os.path.expanduser('~')


def _getMozAddonURI(addonID):
  return 'https://addons.mozilla.org/firefox/downloads/latest/{0}/addon-{0}-latest.xpi?src=ffaddon-installer.py'.format(addonID)


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
    if prefix + 'moz-addon' in yml:
      self.url = _getMozAddonURI(yml['moz-addon'])
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


def CloneOrPull(id, uri, dir):
  if not os.path.isdir(dir):
    cmd(['git', 'clone', uri, dir], echo=True, show_output=True, critical=True)
  else:
    with os_utils.Chdir(dir):
      cmd(['git', 'pull'], echo=True, show_output=True, critical=True)
  with os_utils.Chdir(dir):
    log.info('{} is now at commit {}.'.format(id, Git.GetCommit()))


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
      os_util.safe_rmtree(flint_temp)

  os_utils.ensureDirExists(flint_temp, mode=0o700, noisy=True)

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
        pkg = FFPackage(yml['id'])
        pkg.fromYaml(yml, args)
        pkgs.append(pkg)
    fp = Profile(FF_PROFILE_DIR, restore=False)
    prefs = {k: v for k, v in reversed(Preferences.read_prefs(os.path.join(FF_PROFILE_DIR, 'prefs.js')))}
    for pkg in pkgs:
      pkg.install(fp, args, prefs)
