#!/usr/bin/env python3
"""A4 2ページの要旨（機密）を HTML→PDF で作る。出力は analysis/confidential/briefing/ のみ。"""

import asyncio
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "analysis/confidential/briefing"
D = json.loads((CONF / "deck_data.json").read_text(encoding="utf-8"))
M = D["model"]
clinics = D["clinics"]
judged = [c for c in clinics if c["months"] >= 12 and c["id"] != "honin"]
tight = [c for c in clinics if c["per_fte"] >= 250]
below = [c["name"] for c in clinics if c["months"] >= 6 and c["perf"] <= 0.85]
below_text = f"期待を下回るのは{'・'.join(below)}のみで、他は期待並み以上" if below else "期待を下回る院はない"


def row(c):
    pen = f"{c['penetration']:.0%}" if c in judged else "—"
    perf = f"{c['perf']:.2f}" if c["months"] >= 6 else "—"
    cls = lambda cond: ' class="warn"' if cond else ""
    v = c["verdict"].replace("（月次推移で判定）", "").replace("（判定保留）", "")
    return (
        f"<tr><th>{html.escape(c['name'])}</th><td>{c['months']}</td><td>{c['home']:,}</td><td>{c['facility']:,}</td>"
        f"<td{cls(c['home_mix'] < 0.3)}>{c['home_mix']:.0%}</td><td{cls(c['per_fte'] >= 250)}>{c['per_fte']:.0f}</td>"
        f"<td>{perf}</td><td>{pen}</td><td class='v'>{html.escape(v)}</td></tr>"
    )


sites = "".join(
    f"<tr><td>{i + 1}</td><th>{html.escape(s['area'])}</th><td>{s['underserved_ratio']:.1f}</td><td>{s['competition_density']:.1f}</td>"
    f"<td>{s['pred_home_36m_group_net']:.0f}</td><td>{s['reach_target']:,.0f}</td><td>{html.escape(s['nearest_clinic'])} {s['nearest_clinic_km']:.0f}km</td></tr>"
    for i, s in enumerate(D["top_sites"])
)

page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm 14mm 12mm; }}
body {{ font-family: 'IPAPGothic','IPAGothic','Yu Gothic','Meiryo',sans-serif; color:#1a1a1a; font-size:9.6pt; line-height:1.5; }}
h1 {{ font-size:15pt; color:#0f2d4a; margin:0 0 2mm; }}
h2 {{ font-size:11pt; color:#0f2d4a; margin:5mm 0 1.5mm; }}
.meta {{ color:#6b6a66; font-size:8.5pt; margin-bottom:3mm; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:3mm; }}
.kpi {{ background:#eef3f8; border-radius:2mm; padding:2.5mm 3mm; }}
.kpi b {{ display:block; font-size:17pt; color:#2a78d6; }}
.kpi.o b {{ color:#eb6834; }}
ul {{ margin:1mm 0; padding-left:5mm; }} li {{ margin:0.6mm 0; }}
table {{ border-collapse:collapse; width:100%; font-size:8.6pt; }}
th,td {{ border-bottom:0.3mm solid #d9dee5; padding:1mm 1.5mm; text-align:right; white-space:nowrap; }}
thead th {{ background:#0f2d4a; color:#fff; text-align:center; }}
tbody th {{ text-align:left; }}
td.v {{ text-align:left; white-space:normal; }}
.warn {{ color:#c4501f; font-weight:bold; }}
.note {{ color:#6b6a66; font-size:7.8pt; margin-top:1mm; }}
.pb {{ page-break-before:always; }}
</style></head><body>
<h1>訪問診療データ分析 要旨（理事長面談用・機密）</h1>
<div class="meta">2026年10月／実績は2026年7月時点／半径8km圏・公的統計ベース</div>
<div class="kpis">
<div class="kpi"><b>{M['r2']:.0%}</b>居宅患者数の院間差を「年数・未充足度・立ち上げ方針」で説明（誤差±{M['loo_error_pct']:.0f}%）</div>
<div class="kpi"><b>約3倍</b>埼玉・千葉は同じ年数で東京の約3倍伸びる（未充足度2倍）</div>
<div class="kpi"><b>{max(c['penetration'] for c in judged):.0%}</b>判定可能院の到達率の最大値。上限に当たる院はない</div>
<div class="kpi o"><b>{len(tight)}院</b>医師1人あたり250人超。次の制約は医師</div>
</div>
<h2>結論と提案</h2>
<ul>
<li><b>院の評価</b>は「年数・地域補正後の実力」（実績÷モデル期待値）で。都心と郊外を同じ物差しで比べられる。{below_text}</li>
<li><b>医師配置</b>: {html.escape('・'.join(c['name'] for c in tight))}は伸びしろがあっても医師が先に詰まる。到達率の低い院から増員を優先</li>
<li><b>役割分担</b>: 三鷹・ひばりが丘・高円寺・石神井公園は圏内の半分以上で別のわかさ院が近い。営業エリアの分担を決める</li>
<li><b>出店</b>: 埼玉東部・千葉北西部が上位（未充足度2倍超・競合が薄い・既存院と16km以上離れる）。新規院は居宅重視で立ち上げる（施設重視型は約4割少ない）</li>
<li><b>立ち上げ管理</b>: 地域別の基準カーブで3・6・12か月に判定。浦和・市川から適用</li>
</ul>
<h2>院別の診断</h2>
<table><thead><tr><th>院</th><th>在宅月数</th><th>居宅</th><th>施設</th><th>居宅比</th><th>医師1人あたり</th><th>実力</th><th>到達率</th><th>判定</th></tr></thead>
<tbody>{''.join(row(c) for c in clinics)}</tbody></table>
<div class="note">実力＝実績÷モデル期待値（1.15以上＝期待を上回る、0.85以下＝下回る）。到達率＝実績÷到達目安（本院並みの浸透率×競合密度補正）。赤字＝居宅比30%未満・医師1人あたり250人以上。本院は到達目安の基準のため到達率なし。在宅月数は本院2014-04・所沢2021-06を仮置き</div>
<h2 class="pb">出店候補 上位10地点（1都3県・2km格子）</h2>
<table><thead><tr><th>順位</th><th>地域（格子点に最も近い市区町村）</th><th>未充足度</th><th>競合密度</th><th>3年後予測(純増)</th><th>到達目安</th><th>最寄り既存院</th></tr></thead><tbody>{sites}</tbody></table>
<div class="note">3年後予測は居宅重視で立ち上げた場合。未充足度が実績範囲（最大{M['underserved_range'][1]:.1f}）を超える地点は予測を頭打ちにしているため、順位は主に到達目安で決まる。候補物件の住所があれば site_check.py で即時評価できる</div>
<h2>使った指数（公式採用）</h2>
<ul>
<li><b>未充足度</b> = 東京都並みに普及した場合の居宅需要 ÷ 現在の居宅需要（最も効く予測指数）</li>
<li><b>在宅開始からの月数</b>・<b>立ち上げ方針</b>（施設重視期/転換期）</li>
<li><b>排他率</b> = 8km圏の高齢者のうち自院が最寄りの割合（グループ内の食い合い）</li>
<li><b>競合密度</b> = 在支診・在支病（機能強化型を重く）÷ 75歳以上1万人</li>
<li>人口・需要・競合の「量」そのものは予測に効かない（多いほど居宅が少ない＝都会度の指標）</li>
</ul>
<h2>過去分析からの修正点</h2>
<ul>
<li>手入力の自治体データの誤り（57件中20件）、院の位置のずれ（本院3.8km等）、機能強化型の判定漏れ、県境の受療率、競合座標の欠落を修正。数値は過去資料から変わっている</li>
</ul>
<h2>お願いしたいこと</h2>
<ul>
<li>院別の月次患者数（開院〜現在）→ 各院の上限を成長曲線で確定</li>
<li>紹介元別の新規患者数 → 弱い紹介経路の特定</li>
<li>出店候補物件の住所 → 3年後予測・食い合いをその場で比較</li>
<li>評価会議での「実力」指数の試行</li>
</ul>
</body></html>"""

html_path = CONF / "summary_tmp.html"
html_path.write_text(page, encoding="utf-8")
out = CONF / "わかさ_理事長面談_要旨A4_2026-10.pdf"


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        exe = next((str(x) for x in Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")), None)
        b = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(html_path.as_uri())
        await pg.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
        await b.close()
    html_path.unlink()
    print(out)


asyncio.run(main())
