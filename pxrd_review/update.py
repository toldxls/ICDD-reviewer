#!/usr/bin/env python3
"""
update — is a newer pxrd-review on GitHub, and install it.

    pxrd update              # pip install --upgrade from the main branch (the INSTALL.md one-liner)
    pxrd update --check      # only say whether something newer exists
    pxrd update --release    # the latest GitHub release's wheel instead, hash-verified by pip

The GUI's version chip (top right) runs check() once per session in a background thread and turns
amber when GitHub has a newer version; its tooltip carries the command above. The check sends
nothing but two anonymous GETs (the version file on main, the latest-release record); it gives up
after a few seconds when offline, and PXRD_NO_UPDATE_CHECK=1 turns it off altogether.

Why main and not only the releases: the recommended install line pulls main.zip, so "newest" is
whatever main holds; the releases page lags it (and carries the hash-pinned wheel for those who
want pip to verify the download).
"""
import os, re, sys, json, time, argparse, threading, subprocess, urllib.request

REPO = 'toldxls/ICDD-reviewer'
MAIN_ZIP = 'https://github.com/%s/archive/refs/heads/main.zip' % REPO
MAIN_INIT = 'https://raw.githubusercontent.com/%s/main/pxrd_review/__init__.py' % REPO
RELEASES_URL = 'https://github.com/%s/releases/latest' % REPO
RELEASE_API = 'https://api.github.com/repos/%s/releases/latest' % REPO
TIMEOUT = 5.0

def installed():
    from pxrd_review import __version__
    return __version__

def vtuple(v):
    """'v0.3.4' -> (0, 3, 4); '0.5.1+dirty' -> (0, 5, 1); '' -> ()"""
    return tuple(int(x) for x in re.findall(r'\d+', (v or '').split('+')[0]))

def newer(a, b):
    """True when version a is newer than version b."""
    return vtuple(a) > vtuple(b)

def _ssl_context():
    """macOS python.org builds often ship without CA certs: use certifi's bundle when it is there
    (it is in requirements.txt), else the interpreter's default. Verification is never turned off
    here — this is the channel the tool's own code arrives through."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={'User-Agent': 'pxrd-review/%s' % installed(), 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read().decode('utf-8', 'replace')

def parse_init(text):
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text or '')
    return m.group(1) if m else None

def check(fetch=_get):
    """What GitHub holds vs what is installed. Never raises: an unreachable network leaves the
    fields None and `error` set."""
    out = {'installed': installed(), 'main': None, 'release': None, 'release_url': RELEASES_URL,
           'wheel': None, 'wheel_name': None, 'sha256': None, 'newest': None, 'newer': False, 'error': None}
    errors = []
    try:
        out['main'] = parse_init(fetch(MAIN_INIT))
    except Exception as ex:
        errors.append('main: %s' % ex)
    try:
        j = json.loads(fetch(RELEASE_API))
        out['release'] = (j.get('tag_name') or '').lstrip('vV') or None
        out['release_url'] = j.get('html_url') or RELEASES_URL
        assets = j.get('assets') or []
        whl = next((a for a in assets if str(a.get('name', '')).endswith('.whl')), None)
        sums = next((a for a in assets if 'sha256' in str(a.get('name', '')).lower()), None)
        if whl:
            out['wheel'] = whl.get('browser_download_url'); out['wheel_name'] = whl.get('name')
            if sums and sums.get('browser_download_url'):
                m = re.search(r'([0-9a-fA-F]{64})\s+\*?' + re.escape(whl['name']), fetch(sums['browser_download_url']))
                if m:
                    out['sha256'] = m.group(1).lower()
    except Exception as ex:
        errors.append('release: %s' % ex)
    cands = [v for v in (out['main'], out['release']) if v]
    if cands:
        out['newest'] = max(cands, key=vtuple)
        out['newer'] = newer(out['newest'], out['installed'])
    if errors and not cands:
        out['error'] = '; '.join(errors)
    return out

def pip_command(source='main', info=None):
    """The pip command that upgrades: main.zip (version-less, what INSTALL.md recommends), or the
    latest release's wheel with its sha256 so pip verifies the download."""
    url = MAIN_ZIP
    if source == 'release' and info and info.get('wheel'):
        url = info['wheel'] + ('#sha256=' + info['sha256'] if info.get('sha256') else '')
    return [sys.executable, '-m', 'pip', 'install', '--upgrade', url]

def disabled():
    return os.environ.get('PXRD_NO_UPDATE_CHECK') == '1'

def checkout():
    """The git checkout this pxrd_review is imported from (an editable install or the ./pxrd
    shim), else None. A pip install of main.zip would replace that live link with a plain copy —
    the wrong thing for a developer's machine — so `pxrd update` runs git pull there instead."""
    import pxrd_review
    root = os.path.dirname(os.path.dirname(os.path.abspath(pxrd_review.__file__)))
    return root if os.path.isdir(os.path.join(root, '.git')) and os.path.exists(os.path.join(root, 'pyproject.toml')) else None

# ------------------------------------------------------------------ the GUI's background check
_state = {'status': 'idle', 'result': None}
_lock = threading.Lock()

def start():
    """Kick the check once per process (a daemon thread); status() reports it."""
    with _lock:
        if _state['status'] != 'idle':
            return
        if disabled():
            _state['status'] = 'disabled'; return
        _state['status'] = 'pending'
    def run():
        res = check()
        with _lock:
            _state['result'] = res; _state['status'] = 'done'
    threading.Thread(target=run, daemon=True).start()

def status():
    co = checkout()
    with _lock:
        return {'status': _state['status'], 'installed': installed(), 'result': _state['result'], 'checkout': co,
                'command': 'pxrd update',
                'pip': ('git -C "%s" pull --ff-only' % co) if co else ' '.join(pip_command()[1:]).replace(sys.executable, 'python'),
                'releases_url': RELEASES_URL}

# ------------------------------------------------------------------ the GUI's "Update now"
_run = {'state': 'idle', 'log': '', 'rc': None, 'how': None}
_run_lock = threading.Lock()

def run_status():
    with _run_lock:
        return dict(_run)

def gui_update(gui_argv, env_extra):
    """Update from the GUI and restart it. gui_argv: the server's own arguments (folder, flags);
    env_extra: the token and port the relaunched server must reuse so the open tab reconnects.
    Returns at once; the page polls run_status(). A checkout is pulled; a pip install is upgraded
    from main. POSIX: the server process execs itself afterwards. Windows: the pxrd launcher (our
    parent) locks its own exe, so a helper waits for the tool to exit, runs pip, then reopens it."""
    with _run_lock:
        if _run['state'] in ('running', 'restarting'):
            return dict(_run)
        _run.update(state='running', log='', rc=None, how=None)
    def work():
        co = checkout()
        relaunch = [sys.executable, '-m', 'pxrd_review.gui.review_gui'] + list(gui_argv)
        if '--no-browser' not in relaunch:
            relaunch.append('--no-browser')                   # the open tab reloads; no second tab
        cmd, how = (['git', '-C', co, 'pull', '--ff-only'], 'git pull') if co else (pip_command(), 'pip')
        q = lambda c: '"%s"' % c if ' ' in c else c
        if os.name == 'nt' and not co:
            from pxrd_review import paths as P
            os.makedirs(P.cache_dir(), exist_ok=True)
            script = os.path.join(P.cache_dir(), 'update_and_restart.cmd')
            pid = os.getpid()
            lines = ['@echo off', 'title pxrd update', 'echo Waiting for the tool to close ...', 'timeout /t 3 >nul', ':wait',
                     'tasklist /FI "PID eq %d" 2>NUL | find "%d" >NUL && (timeout /t 1 >nul & goto wait)' % (pid, pid),
                     'echo Installing ...', ' '.join(q(c) for c in cmd),
                     'if errorlevel 1 (echo. & echo The update FAILED - close this window and start the tool again. & pause & exit /b 1)']
            lines += ['set %s=%s' % (k, v) for k, v in env_extra.items()]
            lines += ['echo Starting the tool ...', ' '.join(q(c) for c in relaunch)]
            with open(script, 'w', encoding='utf-8') as f:
                f.write('\r\n'.join(lines) + '\r\n')
            subprocess.Popen(['cmd', '/c', 'start', '"pxrd update"', '/min', script], close_fds=True)
            with _run_lock:
                _run.update(state='restarting', how=how, rc=0,
                            log='pip runs in a separate window once the tool has closed; the tool then reopens by itself.')
            threading.Timer(2.0, lambda: os._exit(0)).start()
            return
        try:
            p = subprocess.run(cmd, capture_output=True, text=True)
            log, rc = (p.stdout + p.stderr)[-4000:], p.returncode
        except OSError as ex:
            log, rc = str(ex), 127
        if rc != 0:
            with _run_lock:
                _run.update(state='failed', rc=rc, log=log, how=how)
            return
        # restart: never exec from this (threaded) process — a detached helper waits for it to
        # exit, which frees the port, then starts a fresh server with the same token and port
        pid = os.getpid()
        script = ('while kill -0 %d 2>/dev/null; do sleep 0.5; done; exec %s'
                  % (pid, ' '.join("'%s'" % c.replace("'", "'\\''") for c in relaunch)))
        env = dict(os.environ); env.update(env_extra)
        try:
            subprocess.Popen(['/bin/sh', '-c', script], env=env, start_new_session=True, close_fds=True)
        except OSError as ex:
            with _run_lock:
                _run.update(state='failed', rc=1, log=log + '\ncould not start the relaunch helper: %s' % ex, how=how)
            return
        with _run_lock:
            _run.update(state='restarting', rc=0, log=log, how=how)
        time.sleep(2.0)                                       # let the page read 'restarting'
        os._exit(0)
    threading.Thread(target=work, daemon=True).start()
    return run_status()

# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog='pxrd update', description=__doc__.split('\n\n')[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='only report; install nothing')
    ap.add_argument('--release', action='store_true', help="install the latest GitHub release's wheel (hash-verified) instead of main")
    ap.add_argument('--force', action='store_true', help='install even when nothing newer exists; on a source checkout, pip-install a copy instead of git pull')
    a = ap.parse_args(argv)
    info = check()
    co = checkout()
    print('installed: pxrd-review %s%s' % (info['installed'], (' (running from the source checkout %s)' % co) if co else ''))
    if info['error']:
        print('could not reach GitHub (%s)\ncheck by hand: %s' % (info['error'], RELEASES_URL))
        return 2
    print('on GitHub: main %s, latest release %s' % (info['main'] or '?', info['release'] or 'none'))
    if co and not a.force:
        # a checkout is updated by git, not pip (pip would replace the live link with a plain copy)
        if a.check:
            print('a git checkout: `pxrd update` pulls it (git pull --ff-only)')
            return 1 if info['newer'] else 0
        print('pulling the checkout (git pull --ff-only) …', flush=True)
        try:
            rc = subprocess.call(['git', '-C', co, 'pull', '--ff-only'])
        except OSError as ex:
            print('git is not available (%s); pull the checkout by hand, or --force to pip-install a copy' % ex)
            return 3
        if rc == 0:
            print('done — restart the tool to use the pulled code.')
        else:
            print('git pull failed (exit %d): resolve it in the checkout (local changes? not fast-forward?), or --force to pip-install a copy' % rc)
        return rc
    if not info['newer']:
        print('up to date — nothing to install.' if not newer(info['installed'], info['newest'] or '0') else
              'this copy (%s) is AHEAD of GitHub (%s) — nothing to install.' % (info['installed'], info['newest']))
        if not a.force:
            return 0
        print('(--force: installing %s over it)' % (info['newest'] or 'main'))
    elif a.check:
        print('NEWER: %s — run  pxrd update  to install it (or --release for the hash-pinned wheel)' % info['newest'])
        return 1
    else:
        print('newer: %s — installing' % info['newest'])
    if a.release and not info.get('wheel'):
        print('the latest release has no wheel asset; installing from main instead')
    cmd = pip_command('release' if a.release else 'main', info)
    shown = ' '.join(cmd).replace(sys.executable, 'python')
    print('running:  %s' % shown, flush=True)
    if os.name == 'nt' and os.environ.get('PXRD_LAUNCHER') == '1':
        # the running `pxrd` launcher locks Scripts\\pxrd.exe: hand pip to a fresh console that
        # starts after this process has gone
        line = ' '.join('"%s"' % c if ' ' in c else c for c in cmd)
        subprocess.Popen(['cmd', '/c', 'start', '"pxrd update"', 'cmd', '/k',
                          'timeout /t 2 >nul & %s & echo. & echo Done - close this window and start the tool again.' % line])
        print('pip is running in a new window; when it finishes, start the tool again.')
        return 0
    rc = subprocess.call(cmd)
    if rc == 0:
        print('done — restart the tool (close the GUI tab or Ctrl-C it, then run it again) to use %s.' % (info['newest'] or 'the new version'))
    else:
        print('pip failed (exit %d). Run the line above by hand — on Windows from a fresh Command Prompt.' % rc)
    return rc

if __name__ == '__main__':
    sys.exit(main())
