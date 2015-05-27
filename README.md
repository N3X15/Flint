# Flint

Deploying Firefox addons can be a pain in the ass, especially if there's lots of PCs to deploy them to.

Flint is a simple thumbdrive-borne tool to to download, deploy, and (eventually) configure these tools automagically for a given user. You can even skip the downloading part by pre-packing your thumbdrive with the required XPIs.  In addition, Flint uses [Mozilla's own testing framework](http://mozbase.readthedocs.org/en/latest/mozprofile.html) to perform the deployment and configuration, so Flint itself is fairly simple and robust.

At the moment, the package database is fairly small, but can be easily extended by the deployer.

# License

Flint is licensed under the MIT Open-Source License.

# Usage

Flint uses two files: `.package.yml` as a simple package database, and *playbooks*.

Playbooks are YAML files listing what packages you wish to install.  You can have multiple playbooks on your thumbdrive, only the one you call will be run.  This way, you can have a playbook for each type of PC you need to set up.  For example, your boss probably doesn't want NoScript breaking Craigslist, while the intern should probably have every possible security addon installed, plus some parental controls. So, you'd have two playbooks: `execs.yml` and `intern.yml`.

Once your playbook is made, you simply make a batch file containing:

```bat
@echo off
call flint playbook.yml
pause
```

Then you chuck that onto a thumbdrive, alongside:
 * `.packages.yml`
 * `playbook.yml`
 * `flint.exe`
 * `packages/*.xpi` (optional, see `flint --help`)

:warning:  **IMPORTANT:** Do NOT have Firefox running during deployment.  Configuration changes will get screwed up, among other things.

# Compiling

Flint requires Python 2.7, PyYaml, configparser, mozprofile, and pyinstaller (which itself requires pywin32).

```
pip install PyYaml configparser mozprofile pyinstaller jinja2 psutil untangle
```

# Issues
Note that there is currently a bug with zope (a distant dependency of my buildtools) that causes zope to crash pyinstaller.  To fix this, add a blank file named `__init__.py` to `C:\Python27\Lib\site-packages\zope`.

After those dependencies are installed, simply run ```build-win.cmd``` to create flint.exe in the dist directory. Note that the first run will take a very long time, as Twisted pulls in a metric assload of dependencies.

# Support

NONE! AHAHAHAHAHA

You can file bug reports and make PRs, though.

# TODO List

 * [ ] Post-install scripts.
 * [ ] Yell at user if they have Firefox running.
