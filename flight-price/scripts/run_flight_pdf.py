#!/usr/bin/env python3
"""End-to-end flight scan + summary + PDF in one command.

Agent protocol: launch this script (foreground or background job), then STOP
and end your turn. The script itself scans every origin/date, retries timed-out
queries once, discards raw data it no longer needs, prints a <500-char summary,
and renders the PDF. On the completion notice, read only the job tail and
deliver the PDF path.

Why not flight_report.py: its PDF path imports reportlab, which is often
missing from minimal Python envs. This script renders PDF with the Playwright
Chromium that ships alongside the `flight-price` CLI, falling back across
interpreters automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_ARGS, EXIT_NO_DATA, EXIT_RENDER = 0, 2, 4, 3
PENGD = {"HKG": "中国香港", "SZX": "深圳", "CAN": "广州", "MFM": "中国澳门", "TYO": "东京",
         "NRT": "东京成田", "HND": "东京羽田", "PEK": "北京首都", "PVG": "上海浦东",
         "SHA": "上海虹桥", "BJS": "北京", "MXP": "米兰", "HGH": "杭州"}
AIR_CN = {"UO": "HK Express", "NH": "全日空", "CX": "国泰", "JL": "日航", "MU": "东航",
          "MF": "厦航", "9C": "春秋", "CA": "国航", "CZ": "南航", "BR": "长荣",
          "TR": "酷航", "VJ": "越捷", "ZE": "易斯达", "LJ": "真航空", "7C": "济州",
          "KE": "大韩", "OZ": "韩亚", "TG": "泰航", "SQ": "新航", "PR": "菲航"}


def esc(x: Any) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cname(code: str) -> str:
    return PENGD.get(code, code)


def air_label(code: str) -> str:
    return f"{AIR_CN.get(code, code)} ({code})" if code else "—"


def dur_txt(mins: int) -> str:
    return f"{mins // 60}h{mins % 60:02d}m" if mins else "—"


def dshort(s: str | None) -> str:
    return s[5:].replace("-", "/") if s else "—"


def find_cli() -> str | None:
    for cand in (shutil.which("flight-price"),
                 Path.home() / ".local/bin/flight-price",
                 Path.home() / ".flight-price-skill/.venv/bin/flight-price"):
        if cand and Path(cand).exists():
            return str(cand)
    return None


def run_query(cli: str, origin: str, dest: str, extra: list[str], out: Path,
              err: Path) -> int:
    cmd = [cli, origin, dest, *extra, "--json"]
    with open(out, "w", encoding="utf-8") as fo, open(err, "w", encoding="utf-8") as fe:
        return subprocess.run(cmd, stdout=fo, stderr=fe).returncode


def load_rows(path: Path, origin: str) -> tuple[list[dict], list[tuple[str, str]], dict]:
    """Return (rows, timeout_pairs, status_counts) from one flight-price JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = {"ok": 0, "no_results": 0, "timeout": 0, "failed": 0}
    pairs: list[tuple[str, str]] = []
    rows: list[dict] = []
    for r in data.get("results", []):
        st = r.get("status", "failed")
        stats[st if st in stats else "failed"] += 1
        if st == "timeout":
            pairs.append((r.get("date"), r.get("return_date")))
    fl = data.get("flights")
    if not fl:  # older/nested layout: results[].options[]
        fl = []
        for r in data.get("results", []):
            if r.get("status") != "ok":
                continue
            for o in r.get("options", []) or []:
                o = dict(o)
                o.setdefault("date", r.get("date"))
                o.setdefault("return_date", r.get("return_date"))
                fl.append(o)
    for f in fl:
        segs = f.get("segments", [])
        direct = f.get("direct")
        if direct is None:
            direct = not f.get("layovers") and len(segs) <= 1
        stops = len(f.get("layovers", [])) or max(len(segs) - 1, 0)
        rows.append({
            "org": origin, "price": f["price"], "cur": f.get("currency", "CNY"),
            "air": f.get("airline") or (f.get("flight_nos") or [""])[0][:2],
            "fn": " ".join(f.get("flight_nos", [])), "dep": f.get("date"),
            "ret": f.get("return_date"), "direct": bool(direct),
            "stops": stops,
            "dur": int(f.get("total_duration_min") or 0),
        })
    return rows, pairs, stats


# ---------------------------------------------------------------- HTML report

def build_html(meta: dict, rows: list[dict]) -> str:
    origins: list[str] = meta["origins"]
    airline_set = set(meta.get("airlines") or [])
    cur = meta["currency"]

    if not rows:
        raise SystemExit(EXIT_NO_DATA)

    per_org = {oc: [r for r in rows if r["org"] == oc] for oc in origins}
    per_org = {oc: v for oc, v in per_org.items() if v}
    best = {oc: min(v, key=lambda r: r["price"]) for oc, v in per_org.items()}
    champ_oc = min(best, key=lambda oc: best[oc]["price"])
    bw = best[champ_oc]
    bway = "直飞" if bw["direct"] else f"中转{bw['stops']}次"

    def card(oc: str) -> str:
        r = best[oc]
        win = oc == champ_oc
        way = "直飞" if r["direct"] else f"中转{r['stops']}次·{dur_txt(r['dur'])}"
        return (f'<div class="card{" win" if win else ""}"><div class="o">'
                f'{esc(cname(oc))} {oc}{" ★最便宜" if win else ""}</div>'
                f'<div class="p">¥{r["price"]:.0f}<span class="c"> {esc(r["cur"])} 往返总价</span></div>'
                f'{esc(air_label(r["air"]))} {esc(r["fn"])} {way}<br>'
                f'{dshort(r["dep"])} 去 · {dshort(r["ret"])} 回</div>')

    # date curve for the champion origin
    by_date: dict[str, dict] = {}
    for r in per_org[champ_oc]:
        k = r["dep"]
        if k not in by_date or r["price"] < by_date[k]["price"]:
            by_date[k] = r
    curve = [by_date[k] for k in sorted(by_date)]
    lo = min(r["price"] for r in curve) if curve else 0

    def drow(r: dict) -> str:
        star = (' <span class="tag">最低</span>' if r["price"] == lo
                else (" <span class='tag2'>低</span>" if r["price"] <= lo * 1.06 else ""))
        air = esc(air_label(r["air"])) if not airline_set else esc(air_label(r["air"]))
        return (f'<tr><td>{dshort(r["dep"])}' + (f" → {dshort(r['ret'])}" if r["ret"] else "") +
                f'</td><td>¥{r["price"]:.0f}{star}</td><td>{air}</td>'
                f'<td>{"直飞" if r["direct"] else "中转"}</td></tr>')

    half = (len(curve) + 1) // 2
    two = (f'<div class="two"><table><tr><th>日期</th><th>往返价</th><th>航司</th><th>停站</th></tr>'
           f'{"".join(drow(r) for r in curve[:half])}</table>'
           f'<table><tr><th>日期</th><th>往返价</th><th>航司</th><th>停站</th></tr>'
           f'{"".join(drow(r) for r in curve[half:])}</table></div>') if curve else ""

    top = sorted(rows, key=lambda r: r["price"])[:10]
    top_rows = "".join(
        f'<tr><td>{i + 1}</td><td>{esc(cname(r["org"]))} {r["org"]}</td>'
        f'<td>¥{r["price"]:.0f}</td><td>{esc(r["fn"])}</td><td>{esc(air_label(r["air"]))}</td>'
        f'<td>{dshort(r["dep"])}{(" → " + dshort(r["ret"])) if r["ret"] else ""}</td>'
        f'<td>{"直飞" if r["direct"] else "中转" + str(r["stops"]) + "次"}</td><td>{dur_txt(r["dur"])}</td></tr>'
        for i, r in enumerate(top))

    rule = ("单程" if meta["trip_type"] == "oneway"
            else f'{meta["stay"] + 1} 天往返（{meta["stay"]} 晚，第 {meta["stay"] + 1} 天回）')
    airl_txt = "、".join(meta["airlines"]) if airline_set else "不限"

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm 12mm; }}
body {{ font-family: "PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
        color:#222; font-size:10.5px; margin:0; }}
h1 {{ font-size:19px; margin:0 0 2px; }} h2 {{ font-size:13px; margin:16px 0 6px;
        border-left:4px solid #e0a800; padding-left:7px; }}
.sub {{ color:#666; margin-bottom:10px; }} table {{ border-collapse:collapse; width:100%; }}
th,td {{ border:1px solid #ddd; padding:3.5px 6px; text-align:left; }} th {{ background:#f5f5f0; }}
.tag {{ background:#e0a800; color:#fff; border-radius:3px; padding:0 4px; font-size:9px; }}
.tag2 {{ background:#eee; color:#888; border-radius:3px; padding:0 4px; font-size:9px; }}
.cards {{ display:flex; gap:8px; flex-wrap:wrap; }}
.card {{ flex:1; min-width:130px; border:1px solid #ddd; border-radius:6px; padding:7px 9px; }}
.card.win {{ border:2px solid #e0a800; background:#fff8e1; }}
.card .p {{ font-size:17px; font-weight:700; }} .card .o {{ font-size:11px; font-weight:600; }}
.card .c {{ font-size:9px; color:#888; font-weight:400; }}
.note {{ color:#777; font-size:9.5px; margin-top:3px; line-height:1.5; }}
.two {{ display:flex; gap:14px; }} .two table {{ width:100%; }} td:last-child {{ white-space:nowrap; }}
</style></head><body>
<h1>{esc(meta["title"])}</h1>
<div class="sub">查询时间 {meta["generated"]} · 数据源 Trip.com（flight-price CLI）· 金额={esc(cur)} 总价 · 1 成人 经济舱</div>
<table><tr><th>行程</th><th>方向</th><th>出发窗口</th><th>机场</th><th>航司</th><th>覆盖查询</th></tr>
<tr><td>{esc(rule)}</td><td>{esc(" → ".join(origins))} → {esc(meta["dest"])}（{esc(cname(meta["dest"]))}）</td>
<td>{meta["depart"]} – {meta["to"]}</td><td>{"、".join(esc(cname(o)) for o in origins)}</td>
<td>{esc(airl_txt)}</td><td>{meta["n_queries"]} 次查询，ok={meta["stats"]["ok"]}{f" no_results={meta['stats']['no_results']}" if meta["stats"]["no_results"] else ""}{f" 超时已重试，剩余超时={meta['stats']['timeout']}" if meta.get("retried") else ""}</td></tr></table>

<h2>① 结论：哪个出发地便宜</h2>
<div class="cards">{''.join(card(oc) for oc in per_org)}</div>
<div class="note">{esc(meta.get("hint") or f"全场最低：{cname(champ_oc)} {champ_oc} ¥{bw['price']:.0f}（{air_label(bw['air'])} {bway}）。机票价格实时浮动，以下单页为准。")}</div>

<h2>② {esc(cname(champ_oc))} {champ_oc} 出发 · 每个出发日最低价</h2>
{two}

<h2>③ 全窗口 TOP 10</h2>
<table><tr><th>#</th><th>出发地</th><th>总价</th><th>去程航班</th><th>航司</th><th>日期</th><th>停站</th><th>去程时长</th></tr>
{top_rows}</table>

<div class="note" style="margin-top:10px">说明：① 价格为查询时刻 Trip.com 可订{esc("往返" if meta["trip_type"] != "oneway" else "单程")}总价（{esc(cur)}），实时浮动，下单前以出票页为准；② 低成本航司（如 UO/TR/VJ/9C）的低档票价托运行李额度通常需加购，具体看出票页；全服务航司一般含托运与餐食，仍以出票页为准；③ 返程日期 = 出发 + {meta["stay"]} 晚（第 {meta["stay"] + 1} 天回）；④ 本报告由 run_flight_pdf.py 自动生成，原始 JSON 已按需清理。</div>
</body></html>"""


# ---------------------------------------------------------------- PDF render

def try_playwright_pdf(html: Path, pdf: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return False
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(html.absolute().as_uri())
        pg.wait_for_timeout(500)
        pg.pdf(path=str(pdf), format="A4", print_background=True,
               margin={"top": "10mm", "bottom": "10mm", "left": "9mm", "right": "9mm"})
        b.close()
    return True


def render_pdf(html: Path, pdf: Path) -> int:
    if try_playwright_pdf(html, pdf):
        print(f"PDF: {pdf}")
        return EXIT_OK
    cands = [str(Path.home() / ".flight-price-skill/.venv/bin/python3"), sys.executable,
             shutil.which("python3") or ""]
    for py in dict.fromkeys(cands):
        if py and Path(py).exists() and os.access(py, os.X_OK):
            if subprocess.run([py, str(Path(__file__).resolve()),
                               "--render-only", str(html), str(pdf)],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == EXIT_OK:
                print(f"PDF: {pdf}")
                return EXIT_OK
    print(f"HTML: {html}\n(no playwright found — PDF skipped, run: flight-price doctor)")
    return EXIT_RENDER


def main() -> int:
    if "--render-only" in sys.argv:  # renderer subprocess: bypass arg validation
        i = sys.argv.index("--render-only")
        try:
            return EXIT_OK if try_playwright_pdf(Path(sys.argv[i + 1]), Path(sys.argv[i + 2])) \
                else EXIT_RENDER
        except Exception:
            return EXIT_RENDER

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("origins", help="comma-separated origin codes, e.g. HKG,SZX,CAN,MFM")
    ap.add_argument("dest")
    ap.add_argument("--trip-type", choices=["roundtrip", "oneway"], default="roundtrip")
    ap.add_argument("--days", type=int, help="trip length incl. both ends (7 -> 6 nights)")
    ap.add_argument("--stay", type=int, help="nights")
    ap.add_argument("--depart", required=True, help="YYYY-MM-DD first departure")
    ap.add_argument("--to", required=True, help="YYYY-MM-DD last departure")
    ap.add_argument("--clamp-return", help="drop dates whose return is after this date")
    ap.add_argument("--airline", help="CLI airline filter, e.g. UO,NH,CX")
    ap.add_argument("--limit", type=int, default=5, help="options kept per query")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--currency")
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--output", help="PDF path")
    ap.add_argument("--title", default="机票比价报告")
    ap.add_argument("--hint", help="custom conclusion line for section 1")
    ap.add_argument("--keep-json", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--render-only", nargs=2, metavar=("HTML", "PDF"),
                    help=argparse.SUPPRESS)
    a = ap.parse_args()

    origins = [o.strip().upper() for o in a.origins.split(",") if o.strip()]
    dest = a.dest.upper()
    if not origins:
        print("no origins"); return EXIT_ARGS
    if a.trip_type == "roundtrip":
        if a.days:
            a.stay = max(a.days - 1, 0)
        if not a.stay:
            print("roundtrip needs --days N or --stay N"); return EXIT_ARGS
    else:
        a.stay = 0
    for s in (a.depart, a.to) + ((a.clamp_return,) if a.clamp_return else ()):
        try:
            date.fromisoformat(s)
        except ValueError:
            print(f"bad date: {s}"); return EXIT_ARGS
    cli = find_cli()
    if not cli:
        print("flight-price CLI not found — install: "
              "https://github.com/daghlny/flight-price-skill"); return EXIT_ARGS

    to_eff = a.to
    if a.clamp_return and a.trip_type == "roundtrip":
        latest = (date.fromisoformat(a.clamp_return) - timedelta(days=a.stay)).isoformat()
        to_eff = min(to_eff, latest)

    work = Path(tempfile.mkdtemp(prefix="fpdf-", dir=a.output and str(Path(a.output).parent) or None))
    common = ["--sort", "price", "--limit", str(a.limit), "--concurrency", str(a.concurrency)]
    if a.airline:
        common += ["--airline", a.airline]
    if a.currency:
        common += ["--currency", a.currency]
    if a.cache:
        common += ["--cache"]
    scan_extra = (["--rt", "--stay", str(a.stay)] if a.trip_type == "roundtrip" else []) + \
                 ["--from", a.depart, "--to", to_eff] + common

    rows, seen, stats, retried, still_to, nq = [], set(), {"ok": 0, "no_results": 0,
                                                           "timeout": 0, "failed": 0}, 0, 0, 0
    for oc in origins:
        out, err = work / f"{oc}.json", work / f"{oc}.err"
        rc = run_query(cli, oc, dest, scan_extra, out, err)
        if rc != 0:
            stats["failed"] += 1
            continue
        rws, pairs, st = load_rows(out, oc)
        nq += len(pairs) + st["ok"] + st["no_results"]
        for k in st:
            stats[k] += st[k]
        for r in rws:
            key = (r["org"], r["dep"], r["ret"], r["price"], r["fn"])
            if key not in seen:
                seen.add(key)
                rows.append(r)
        if pairs:  # one targeted retry, pairs mode
            pr = ",".join(f"{d}{(':' + rd) if rd else ''}" for d, rd in pairs)
            rout, rerr = work / f"{oc}-retry.json", work / f"{oc}-retry.err"
            if run_query(cli, oc, dest, ["--pairs", pr] + common, rout, rerr) == 0:
                retried += len(pairs)
                stats["timeout"] -= len(pairs)  # re-tallied by retry outcome
                rws, _, st = load_rows(rout, oc)
                for k in st:
                    stats[k] += st[k]
                still_to += st["timeout"]
                nq += len(pairs)
                for r in rws:
                    key = (r["org"], r["dep"], r["ret"], r["price"], r["fn"])
                    if key not in seen:
                        seen.add(key)
                        rows.append(r)

    if not rows:
        print(f"no usable data — stats={stats}; run: flight-price doctor")
        shutil.rmtree(work, ignore_errors=True)
        return EXIT_NO_DATA

    meta = {
        "title": a.title, "origins": origins, "dest": dest,
        "trip_type": a.trip_type, "stay": a.stay, "days": a.stay + 1,
        "depart": a.depart, "to": to_eff, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "currency": rows[0]["cur"] if not a.currency else a.currency,
        "airlines": a.airline.upper().split(",") if a.airline else [],
        "n_queries": nq, "stats": stats, "retried": retried, "hint": a.hint,
    }
    html = (work / "report.html")
    html.write_text(build_html(meta, rows), encoding="utf-8")

    pdf = Path(a.output) if a.output else Path.cwd() / (
        f"flight-report-{'-'.join(origins)}-{dest}-{a.depart}_{to_eff}.pdf")
    rc = EXIT_OK
    final_html = pdf.with_suffix(".html")
    if not a.no_pdf:
        pdf.parent.mkdir(parents=True, exist_ok=True)
        rc = render_pdf(html, pdf)
    shutil.move(str(html), str(final_html))
    html = final_html
    if rc == EXIT_RENDER:
        print(f"HTML kept at {html}")

    # compact agent-facing summary (keep < 500 chars)
    per_org = {}
    for r in sorted(rows, key=lambda r: r["price"]):
        per_org.setdefault(r["org"], r)
    lines = [f"{oc} best ¥{r['price']:.0f} {r['air']} {r['fn']} {dshort(r['dep'])}~{dshort(r['ret'])}"
             f"{' 直飞' if r['direct'] else ' 中转'}" for oc, r in per_org.items()]
    print(" | ".join(lines))
    print(f"queries ok={stats['ok']} no_results={stats['no_results']}"
          + (f" retried={retried} still_timeout={still_to}" if retried else "")
          + f" | rows={len(rows)} | {html}")
    if a.keep_json:
        merged = []
        for p in sorted(work.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            fls = d.get("flights")
            if not fls:
                fls = [o for r in d.get("results", []) if r.get("status") == "ok"
                       for o in r.get("options", []) or []]
            merged.extend(fls)
        keep = pdf.with_name(pdf.stem + "-raw.json")
        keep.write_text(json.dumps({"flights": merged}, ensure_ascii=False), encoding="utf-8")
        print(f"raw: {keep}")
    shutil.rmtree(work, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
