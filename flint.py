'''
This is intended to be compiled with pyinstaller.
'''

import os
import sys
import argparse
import yaml
import configparser

from selenium import webdriver

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, 'lib', 'buildtools'))

from buildtools import cmd, log, http
from buildtools import os_utils
from buildtools.wrapper import Git
from buildtools.bt_logging import IndentLogger

home_dir = os.path.expanduser('~')


def _getMozAddonURI(addonID):
  return 'https://addons.mozilla.org/firefox/downloads/latest/{0}/addon-{0}-latest.xpi?src=ffaddon-installer.py'.format(addonID)

PACKAGES = {
    'noscript': FFPackage('noscript', 'NoScript', _getMozAddonURI(722), 'noscript.xpi'),
    'dlbar': FFPackage('dlbar', 'Download Bar', _getMozAddonURI(476246), 'dlbar.xpi'),
    'adblock': FFPackage('adblock', 'AdBlock Plus', 'https://update.adblockplus.org/latest/adblockplusfirefox.xpi', 'adblockplus.xpi'),
    'mega': FFPackage('mega', 'Mega Sync', 'https://mega.co.nz/mega.xpi', 'mega.xpi'),
}

FF_APPDATA_DIR = ''
FF_PROFILE_DIR = ''
FF_PROFILE_INI = ''


def locateFirefoxDirs():
  if sys.platform == 'win32':
    FF_APPDATA_DIR = os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox')
  else:
    FF_APPDATA_DIR = os.path.join(home_dir, '.mozilla', 'firefox')
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
  for section in ini.sections():
    for key in ini.items(section):
      if key == 'Default':
        FF_PROFILE_DIR = ini.get(section, 'Path')
        if ini.getboolean(section, 'IsRelative'):
          FF_PROFILE_DIR = os.path.join(FF_PROFILE_DIR, path)
  log.info('Profile: %s', FF_PROFILE_DIR)


class FFPackage(object):

  def __init__(self, _id, name, url, filename=None, config={}):
    self.id = _id
    self.name = ''
    self.url = ''
    self.filename = filename
    self.config = config

  def fromYaml(self, yml):
    self.name = yml['name']
    self.url = yml['url']
    self.filename = yml['filename']
    self.config = yml.get('config', {})

  def install(self, fp, args):
    with log.info('Installing %s:', self.name):
      if not os.path.isfile(self.filename):
        if args.dry_run:
          log.info('Would download %s from %s.', self.filename, self.url)
        else:
          with log.info('Downloading %s...', self.filename):
            http.DownloadFile(self.url, self.filename)
      if args.dry_run:
        log.info('Would install %s.', self.filename)
      else:
        with log.info('Installing %s...', self.filename):
          fp.add_extension(extension=self.filename)

      if len(self.config) > 0:
        with log.info('Configuring...'):
          for k, v in self.config.items():
            if args.dry_run:
              log.info('Would set %s to %r', k, v)
            else:
              fp.set_preference(k, v)


def CloneOrPull(id, uri, dir):
  if not os.path.isdir(dir):
    cmd(['git', 'clone', uri, dir], echo=True, show_output=True, critical=True)
  else:
    with os_utils.Chdir(dir):
      cmd(['git', 'pull'], echo=True, show_output=True, critical=True)
  with os_utils.Chdir(dir):
    log.info('{} is now at commit {}.'.format(id, Git.GetCommit()))


if __name__ == '__main__':
  argp = argparse.ArgumentParser(prog='tome', description='Installer for Arcanist.', version=TOME_VERSION)
  argp.add_argument('configfile', type=argparse.FileType('r'), help='YAML configuration file.')
  argp.add_argument('--dry-run', action='store_true', default=False, help='Do not install addons, just go through the motions.')

  args = argp.parse_args()

  cfg = {}
  with log.info('Loading %s...', args.configfile.name):
    cfg = yaml.load(args.configfile)

  with log.info('Installing addons...'):
    pkgs = []
    for aspec in cfg.get('addons', {}):
      pkg = None
      if isinstance(aspec, (str, unicode)):
        pkg = PACKAGES[aspec]
      if isinstance(aspec, dict):
        pkg = FFPackage(aspec['id'])
        pkg.fromYaml(yml)
      if pkg:
        pkgs.append(pkg)
    fp = webdriver.FirefoxProfile(FF_PROFILE_DIR)
    for pkg in pkgs:
      pkg.install(fp, args)
    browser = webdriver.Firefox(firefox_profile=fp)
