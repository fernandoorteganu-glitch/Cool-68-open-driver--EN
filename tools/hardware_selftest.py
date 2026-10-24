"""Check the driver against a real COOL 68, then put every setting back.

    python tools/hardware_selftest.py --yes

It writes temporary values (a remapped key, a key's actuation point, a lighting change, a profile
switch, a polling-rate change) and restores each one in a `finally` block. Close the COOL 68 Control
Center app and the vendor app first: only one program can use the configuration interface at a time.
The polling-rate test makes the keyboard disappear from USB for a moment; that is expected.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import cool68  # noqa: E402
from cool68 import Cool68, basic_key  # noqa: E402

results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(("PASS  " if condition else "FAIL  ") + name, flush=True)


def reopen(kb, wait=12.0):
    """Close and reopen the connection (the keyboard re-enumerates after a polling-rate change)."""
    try:
        kb.close()
    except Exception:
        pass
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        try:
            return Cool68()
        except Exception:
            continue
    raise RuntimeError("keyboard did not come back on USB")


def restore_light(kb, st):
    """With multicolour on the keyboard ignores the colour, so store the colour first with it off."""
    kb.set_light(st["mode"], st["r"], st["g"], st["b"], st["brightness"], st["speed"], False)
    if st["mix_mask"]:
        kb.set_light(st["mode"], st["r"], st["g"], st["b"], st["brightness"], st["speed"], st["mix_mask"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="confirm that temporary writes to the keyboard are fine")
    ap.add_argument("--skip-polling", action="store_true", help="do not change the polling rate")
    args = ap.parse_args()
    if not args.yes:
        sys.exit("Refusing to run without --yes (this writes temporary settings to the keyboard).")

    kb = Cool68()
    prec = kb.get_precision()[1]
    print(f"connected: firmware 0x{kb.get_firmware_version():04X}, precision {prec}\n")

    # ---- keymap
    orig = kb.get_keymap(0, [98])[98]
    try:
        kb.set_key(0, 98, basic_key(0x68))                         # Insert -> F13
        check("keymap: write and read back", kb.get_keymap(0, [98])[98] == 0x68)
    finally:
        kb.set_key(0, 98, orig)
    check("keymap: restored", kb.get_keymap(0, [98])[98] == orig)

    # ---- layer restore button
    fn0 = kb.get_keymap(1)
    try:
        kb.set_key(1, 28, 0x04)
        kb.restore_layer(1)
        check("keymap: restore_layer(1) puts the Fn layer back", kb.get_keymap(1) == fn0 == cool68.FACTORY_KEYMAP[1])
    finally:
        kb.set_keys(1, fn0)

    # ---- travel / rapid trigger / dead zone
    t0, r0, s0 = kb.get_travel([1])[1], kb.get_rapid_trigger([1])[1], kb.get_safe_area([1])[1]
    try:
        kb.set_travel({1: (cool68.mm_to_raw(1.5, prec), False)})
        kb.set_rapid_trigger({1: dict(enable=True, up=30, down=30, use_global=False)})
        kb.set_safe_area({1: dict(up=10, down=10, use_global=False, enable=True)})
        check("hall settings: write and read back", kb.get_travel([1])[1][0] == cool68.mm_to_raw(1.5, prec)
              and kb.get_rapid_trigger([1])[1]["enable"] and kb.get_safe_area([1])[1]["enable"])
    finally:
        kb.set_travel({1: t0})
        kb.set_rapid_trigger({1: r0})
        kb.set_safe_area({1: s0})
    check("hall settings: restored", (kb.get_travel([1])[1], kb.get_rapid_trigger([1])[1], kb.get_safe_area([1])[1]) == (t0, r0, s0))

    # ---- backlight and per-key colours
    light0, colors0 = kb.get_light(), kb.get_key_colors()
    try:
        kb.set_light(1, 10, 200, 90, 20, 2, False)
        got = kb.get_light()
        check("lighting: mode and colour", got["mode"] == 1 and (got["r"], got["g"], got["b"]) == (10, 200, 90))
        kb.set_light(cool68.LIGHT_CUSTOM, 255, 255, 255, 20, 2, False)
        kb.set_key_colors({1: (255, 0, 0), 70: (0, 0, 255)})
        got = kb.get_key_colors([1, 70])
        check("per-key colours: write and read back", got[1] == (255, 0, 0) and got[70] == (0, 0, 255))
    finally:
        kb.set_key_colors(colors0)
        restore_light(kb, light0)
    check("lighting and per-key colours: restored", kb.get_key_colors() == colors0 and kb.get_light() == light0)

    # ---- advanced keys
    try:
        kb.set_toggle_key(0, 98, basic_key(0x68))
        kb.set_mod_tap_key(0, 98, basic_key(0x68), basic_key(0x69), 200)
        check("advanced key: mod-tap write and read back", kb.get_advanced_key(0, 98)["type"] == "mod_tap")
    finally:
        for pos in kb.list_advanced_keys(0):
            kb.remove_advanced_key(0, pos)
    check("advanced keys: all removed", kb.list_advanced_keys(0) == [])

    # ---- settings
    lock0 = kb.get_win_lock()
    try:
        kb.set_win_lock(not lock0)
        check("settings: win-lock toggles", kb.get_win_lock() == (not lock0))
    finally:
        kb.set_win_lock(lock0)

    # ---- profiles
    p0 = kb.get_profile()
    other = (p0 + 1) % 3
    try:
        kb.set_profile(other)
        time.sleep(0.5)
        check("profiles: switch", kb.get_profile() == other)
    finally:
        kb.set_profile(p0)
        time.sleep(0.5)
    check("profiles: switched back", kb.get_profile() == p0)

    # ---- polling rate (the keyboard may re-enumerate)
    if not args.skip_polling:
        hz0 = kb.get_polling()
        new = 1000 if hz0 != 1000 else 2000
        try:
            kb.set_polling(new)
            kb = reopen(kb)
            check(f"polling: {hz0} -> {new} Hz", kb.get_polling() == new)
        finally:
            try:
                kb.set_polling(hz0)
            except Exception:
                kb = reopen(kb)
                kb.set_polling(hz0)
            kb = reopen(kb)
        check("polling: restored", kb.get_polling() == hz0)

    # ---- live travel stream (no key needs to be pressed)
    try:
        kb.live_start([30])
        time.sleep(1.0)
        events = kb.live_poll()
        check("live stream: reports arrive", len(events) > 0)
    finally:
        kb.live_stop()

    kb.close()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
