#!/usr/bin/env python3
"""Attach a clickable local-file link (the downloaded "ebook" / expediente PDF)
to a remates CSV row, matched by Causa (RIT).

Adds an `Ebook` column if missing and, for every row whose Causa matches, writes
an Excel HYPERLINK formula pointing at the local PDF. The link uses a path
RELATIVE to the CSV, so it keeps working if you move the whole `pjub` folder.
Excel evaluates the formula on open -> the cell is a clickable link.

Usage:
    python link_ebook.py --causa C-81-2026 \
        --file docs/pjud_C-81-2026_Laja_TESORERIA-OYARCE_ebook.pdf \
        --label "Ebook C-81-2026 (Laja)"
    # options: --csv remates_2026-08-23.csv  (default = newest remates_*.csv)
"""

import argparse
import csv
import glob
import os
import sys

EBOOK_COL = "Ebook"


def newest_csv():
    files = sorted(glob.glob("remates_*.csv"), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--causa", required=True, help="RIT to match, e.g. C-81-2026")
    ap.add_argument("--file", required=True, help="path to the PDF, relative to the CSV")
    ap.add_argument("--label", default="", help="link text (default: 'Ebook <causa>')")
    ap.add_argument("--csv", default="", help="target CSV (default: newest remates_*.csv)")
    a = ap.parse_args()

    path = a.csv or newest_csv()
    if not path or not os.path.exists(path):
        sys.exit("No target CSV found.")
    # verify the linked file actually exists next to the CSV
    csv_dir = os.path.dirname(os.path.abspath(path))
    if not os.path.exists(os.path.join(csv_dir, a.file)):
        sys.exit(f"Linked file not found: {os.path.join(csv_dir, a.file)}")

    label = a.label or f"Ebook {a.causa}"
    rel = a.file.replace("\\", "/")                       # forward slashes for Excel
    formula = f'=HYPERLINK("{rel}","{label}")'

    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    if EBOOK_COL not in header:
        header.append(EBOOK_COL)
        body = [r + [""] for r in body]
    ci_causa = header.index("Causa")
    ci_ebook = header.index(EBOOK_COL)

    n = 0
    for r in body:
        while len(r) < len(header):
            r.append("")
        if r[ci_causa].strip() == a.causa.strip():
            r[ci_ebook] = formula
            n += 1

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(f"Linked {n} row(s) for Causa {a.causa} -> {rel}  in {path}")
    if n == 0:
        print("WARNING: no matching Causa row found.")


if __name__ == "__main__":
    main()
