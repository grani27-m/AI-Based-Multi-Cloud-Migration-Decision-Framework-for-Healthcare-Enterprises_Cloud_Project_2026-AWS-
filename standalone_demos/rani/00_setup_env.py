"""
00 - Create .env with random secrets (run once on a new laptop).

    python 00_setup_env.py            # refuses to overwrite an existing .env
    python 00_setup_env.py --force

Prints the generated demo passwords once; they are stored only in .env (git-ignored).
"""

from __future__ import annotations

import argparse
import secrets

from demo_common import ROOT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    env = ROOT / ".env"
    if env.exists() and not a.force:
        print(".env already exists (use --force to regenerate)")
        return 0
    vals = {"SECRET_KEY": secrets.token_hex(32), "BOOTSTRAP_ADMIN_PASSWORD": "Admin-" + secrets.token_urlsafe(9),
            "DOCTOR_PASSWORD": "Doctor-" + secrets.token_urlsafe(9), "DEVICE_PASSWORD": "Device-" + secrets.token_urlsafe(9)}
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        k = line.split("=", 1)[0]
        lines.append(f"{k}={vals[k]}" if k in vals else line)
    env.write_text("\n".join(lines) + "\n")
    print("Created .env. Demo accounts (also stored in .env):")
    print(f"  admin      / {vals['BOOTSTRAP_ADMIN_PASSWORD']}")
    print(f"  doctor     / {vals['DOCTOR_PASSWORD']}")
    print(f"  sim-device / {vals['DEVICE_PASSWORD']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
