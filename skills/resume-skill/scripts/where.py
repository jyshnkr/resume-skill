#!/usr/bin/env python3
"""Print where the user's resume data folder is, and where that answer came from. Never creates anything.

    python3 where.py [--json]

Order: the RESUME_SKILL_DATA environment variable, then the folder saved by setup in
~/.config/resume-skill/location, then the default ~/.config/resume-skill/data/.
(RESUME_SKILL_CONFIG_DIR replaces ~/.config/resume-skill, mainly for tests.)

Exit 0: the folder is ready (it holds settings.yaml, settings.yml or the older settings.json). Output: its path, then "source: env|saved|default".
Exit 1: something is set but wrong (mistyped variable, saved folder gone, folder is not a data folder).
Exit 2: nothing is set up yet. Ask the user where the data should live, then run setup.py.
"""
import json, os, sys

SETTINGS_FILES = ("settings.yaml", "settings.yml", "settings.json")  # the first one found is the user's settings
MARKER = "settings.yaml"  # the name used in messages
ENV = "RESUME_SKILL_DATA"


def config_dir():
    return os.path.abspath(os.path.expanduser(os.environ.get("RESUME_SKILL_CONFIG_DIR") or "~/.config/resume-skill"))


def saved_location():
    f = os.path.join(config_dir(), "location")
    if os.path.isfile(f):
        with open(f, encoding="utf-8") as fh:
            return fh.read().strip() or None
    return None


def has_settings(path):
    return any(os.path.isfile(os.path.join(path, n)) for n in SETTINGS_FILES)


def resolve():
    """Returns dict(path, source, saved, state). state is ready | missing | not_data | unset. Creates nothing."""
    saved = saved_location()
    env = os.environ.get(ENV)
    if env:
        path, source = os.path.abspath(os.path.expanduser(env)), "env"
    elif saved:
        path, source = os.path.abspath(os.path.expanduser(saved)), "saved"
    else:
        path, source = os.path.join(config_dir(), "data"), "default"
    if has_settings(path):
        state = "ready"
    elif os.path.isdir(path):
        state = "not_data" if (source != "default" or os.listdir(path)) else "unset"
    else:
        state = "missing" if source != "default" else "unset"
    return {"path": path, "source": source, "saved": saved, "state": state}


def data_root():
    """For the other scripts: the ready data folder, or exit with the same message where.py gives."""
    r = resolve()
    if r["state"] != "ready":
        raise SystemExit(message(r))
    return r["path"]


def message(r):
    name = {"env": f"{ENV}", "saved": f"the saved location ({os.path.join(config_dir(), 'location')})", "default": "the default folder"}[r["source"]]
    if r["state"] == "missing":
        return f"error: {name} points to {r['path']}, which does not exist. Fix it or run setup.py --data PATH --yes."
    if r["state"] == "not_data":
        return f"error: {r['path']} (from {name}) is not a resume-skill data folder: it has no {MARKER} (or the older settings.json)."
    if r["state"] == "unset":
        return f"no data folder yet (looked at {r['path']}). Ask the user where it should live, then run: setup.py --data PATH --yes"
    return ""


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    r = resolve()
    if "--json" in a:
        print(json.dumps({k: r[k] for k in ("path", "source", "saved", "state")}))
    elif r["state"] == "ready":
        print(r["path"])
        print(f"source: {r['source']}")
        if r["saved"] and r["source"] == "env" and os.path.abspath(os.path.expanduser(r["saved"])) != r["path"]:
            print(f"also saved: {r['saved']} (the {ENV} variable wins)")
    if r["state"] != "ready":
        print(message(r), file=sys.stderr)
    return 0 if r["state"] == "ready" else 2 if r["state"] == "unset" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
