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
MM = D.get("monthly") or {}
ym = lambda m: f"{m[:4]}年{int(m[5:])}月"  # noqa: E731
stalled = [c for c in clinics if c["verdict"].startswith("停滞")]
full = [c for c in stalled if c["penetration"] >= 0.8]
room = [c for c in stalled if c["penetration"] < 0.8]
P = D["peer"]
F = D.get("flow") or {}
FC = F.get("clinics", {})
cause_of = lambda c: FC.get(c["name"], {}).get("stall_cause") or ""  # noqa: E731
bA = [c for c in stalled if cause_of(c).startswith("A")]
bB = [c for c in stalled if cause_of(c).startswith("B")]
jn = lambda arr: html.escape("・".join(c["name"] for c in arr))  # noqa: E731
below = [c["name"] for c in clinics if c["months"] >= 6 and c["perf"] <= 0.85]
below_text = f"期待を下回るのは{'・'.join(below)}のみで、他は期待並み以上" if below else "期待を下回る院はない"


def row(c):
    pen = "先行者" if c["id"] == "honin" else (f"{c['penetration']:.0%}" if c["months"] >= 12 else "—")
    perf = f"{c['perf']:.2f}" if c["months"] >= 6 else "—"
    cls = lambda cond: ' class="warn"' if cond else ""
    v = c["verdict"].replace("（月次推移で判定）", "").replace("（判定保留）", "")
    return (
        f"<tr><th>{html.escape(c['name'])}</th><td>{c['months']}</td><td>{c['home']:,}</td><td>{c['facility']:,}</td>"
        f"<td{cls(c['home_mix'] < 0.3)}>{c['home_mix']:.0%}</td><td>{c['area_type']}</td>"
        f"<td>{perf}</td><td>{pen}</td><td class='v'>{html.escape(v)}</td></tr>"
    )


sites = "".join(
    f"<tr><td>{i + 1}</td><th>{html.escape(s['area'])}</th><td>{s['underserved_ratio']:.1f}</td><td>{s['competition_density']:.1f}</td>"
    f"<td>{s['pred_home_36m_group_net']:.0f}</td><td>{s['reach_target']:,.0f}</td><td>{html.escape(s['nearest_clinic'])} {s['nearest_clinic_km']:.0f}km</td></tr>"
    for i, s in enumerate(D["top_sites"])
)

if F:
    FLOW_ITEMS = (
        f"<li><b>新規と終了</b>: 居宅は毎月患者の約{100 * F['group_end_rate_home']:.1f}%が終了（平均在籍約{1 / F['group_end_rate_home']:.0f}か月）。"
        f"患者数は「月間新規÷終了率」に落ち着くため、グループの居宅新規 月{F['group_new_home_m']:.0f}人（2024年夏から横ばい）のままなら"
        f"居宅は約{round(F['group_eq_home'], -2):,.0f}人で頭打ち（現在{MM['home_last']:,}人）。2024年までに開院した9院の居宅新規は"
        f"月{F['new_home_by_year']['2024']['既存院']:.0f}→{F['new_home_by_year']['2026']['既存院']:.0f}人に減り、新しい院が補っている</li>"
        f"<li><b>停滞院の原因（新規・終了で確認）</b>: 停滞{len(stalled)}院はいずれも均衡に到達済みで、終了率は他院並み（終了の多さは原因ではない）。"
        f"{jn(bA)}は新規が担当エリアの大きさに見合う＝<b>エリアを取り切った</b> → 担当エリアの再設定・隣接地域の開拓。"
        f"{jn(bB)}は<b>新規が少ない</b>（エリアの大きさ比で上位院の{'・'.join(format(FC[c['name']]['inflow_vs_ref'], '.0%') for c in bB)}）"
        f" → 紹介経路の立て直し（到達目安に必要な新規は月{'・'.join(format(FC[c['name']]['new_home_needed'], '.0f') for c in bB)}人）</li>"
    )
    KPI4 = (f'<div class="kpi o"><b>月{F["group_new_home_m"]:.0f}人</b>グループの居宅新規。2024年夏から横ばいで、'
            f'このままなら居宅は約{round(F["group_eq_home"], -2):,.0f}人で頭打ち</div>')
else:
    FLOW_ITEMS = (f"<li><b>停滞院の2タイプ</b>: {jn(full)}は担当エリアを取り込み済み → エリアの再設定。"
                  f"{jn(room)}はエリア内に余地 → 紹介経路の強化</li>")
    KPI4 = f'<div class="kpi o"><b>{len(full)}院</b>うち担当エリアを同条件の上位院並みに取り込み済み（{jn(full)}）</div>'

_g = [c["e85_growth_25_35"] for c in clinics]
G85_LO, G85_HI = round(10 * (min(_g) - 1)), round(10 * (max(_g) - 1))
G85_OUT = round(100 * (sum(c["e85_growth_25_35"] for c in clinics if c["pref"] != "東京都") / sum(1 for c in clinics if c["pref"] != "東京都") - 1))
G85_TKY = round(100 * (sum(c["e85_growth_25_35"] for c in clinics if c["pref"] == "東京都") / sum(1 for c in clinics if c["pref"] == "東京都") - 1))
MIN_KM = int(min(t["nearest_clinic_km"] for t in D["top_sites"]))

page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm 14mm 12mm; }}
body {{ font-family: 'IPAPGothic','IPAGothic','Yu Gothic','Meiryo',sans-serif; color:#1a1a1a; font-size:8.9pt; line-height:1.4; }}
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
<div class="meta">2026年10月／実績は{ym(MM["last_month"]) if MM else "2026年7月"}末時点（月次は{ym(MM["first_month"]) if MM else "—"}〜）／半径{M.get("radius_km", 8):g}km圏・公的統計ベース</div>
<div class="kpis">
<div class="kpi"><b>{MM["home_last"] / MM["home_first"]:.1f}倍</b>グループの居宅（{MM["home_first"]:,}→{MM["home_last"]:,}人）。施設は2025年春から横ばい</div>
<div class="kpi"><b>{M['r2']:.0%}</b>居宅患者数の院間差を「年数・未充足度・立ち上げ方針」で説明（誤差±{M['loo_error_pct']:.0f}%）</div>
<div class="kpi o"><b>{len(stalled)}院</b>居宅が直近6か月伸びていない（{html.escape('・'.join(c['name'] for c in stalled))}）</div>
{KPI4}
</div>
<h2>結論と提案</h2>
<ul>
{FLOW_ITEMS}
<li><b>背景</b>: 診療報酬改定ごとに施設を抑える方針。施設型で立ち上げた院ほど居宅の獲得の仕組みが育っておらず（同条件で居宅が約{round((1-__import__('math').exp(M['coef']['d_facility_era']))*100)}%少ない）、施設の伸びが止まると全体も止まる</li>
<li><b>比較の基準</b>: 本院は先行者のため除外し、同じ地域タイプの上位院（都市型: {html.escape('・'.join(P['都市型']['members']))}、未充足型: {html.escape('・'.join(P['未充足型']['members']))}）と比べた。医師数は患者に合わせて増やす運用のため、原因ではなく増員時期の目安として扱う</li>
<li><b>浦和</b>: {[c for c in clinics if c['id']=='urawa'][0]['months']}か月で居宅{[c for c in clinics if c['id']=='urawa'][0]['home']}人。地域条件からの基準の約{[c for c in clinics if c['id']=='urawa'][0]['perf']:.0%}で、立ち上げ支援が必要</li>
<li><b>データ補正（確認済み）</b>: 2025年4月の石神井公園・三鷹→高円寺の施設移管、2025年8月の報告値の修正を除いた実態ベースで評価。居宅は全院・全期間でがん医総を含めて統一（市川も）。本院の施設減は補正せず</li>
<li><b>院の評価</b>は「年数・地域補正後の実力」（実績÷モデル期待値）で。都心と郊外を同じ物差しで比べられる。{below_text}</li>
<li><b>10年後</b>: 85歳以上は2035年までに各院の圏域で{G85_LO}〜{G85_HI}割増。埼玉・千葉の院（平均+{G85_OUT}%）は都内の院（+{G85_TKY}%）より速い</li>
<li><b>出店</b>: 埼玉東部・千葉北西部が上位（未充足度2倍超・競合が薄い・既存院と{MIN_KM}km以上離れる）。新規院は居宅重視で立ち上げる（施設重視型は約4割少ない）</li>
</ul>
<h2>院別の診断</h2>
<table><thead><tr><th>院</th><th>在宅月数</th><th>居宅</th><th>施設</th><th>居宅比</th><th>地域タイプ</th><th>実力</th><th>上位院比</th><th>判定</th></tr></thead>
<tbody>{''.join(row(c) for c in clinics)}</tbody></table>
<div class="note">実力＝実績÷モデル期待値（1.15以上＝期待を上回る、0.85以下＝下回る。本院を除く院で推定）。上位院比＝自院が最寄りの潜在居宅需要の取り込み率÷同じ地域タイプの上位2院の平均。赤字＝居宅比30%未満。本院は先行者のため比較対象外。在宅月数は本院2014-04・所沢2021-06を仮置き</div>
<h2 class="pb">出店候補 上位10地点（1都3県・2km格子）</h2>
<table><thead><tr><th>順位</th><th>地域（格子点に最も近い市区町村）</th><th>未充足度</th><th>競合密度</th><th>3年後予測(純増)</th><th>到達目安</th><th>最寄り既存院</th></tr></thead><tbody>{sites}</tbody></table>
<div class="note">3年後予測は居宅重視で立ち上げた場合。未充足度が実績範囲（最大{M['underserved_range'][1]:.1f}）を超える地点は予測を頭打ちにしているため、順位は主に到達目安で決まる。候補物件の住所があれば site_check.py で即時評価できる</div>
<h2>使った指数（公式採用）</h2>
<ul>
<li><b>未充足度</b> = 東京都並みに普及した場合の居宅需要 ÷ 現在の居宅需要（最も効く予測指数）</li>
<li><b>在宅開始からの月数</b>・<b>立ち上げ方針</b>（施設重視期/転換期）</li>
<li><b>排他率</b> = {M.get("radius_km", 8):g}km圏の高齢者のうち自院が最寄りの割合（グループ内の食い合い）</li>
<li><b>競合密度</b> = 在支診・在支病（機能強化型を重く）÷ 75歳以上1万人</li>
<li>人口・需要・競合の「量」そのものは予測に効かない（多いほど居宅が少ない＝都会度の指標）</li>
</ul>
<h2>過去分析からの修正点</h2>
<ul>
<li>手入力の自治体データの誤り（57件中20件）、院の位置のずれ（本院3.8km等）、機能強化型の判定漏れ、県境の受療率、競合座標の欠落（→100%補完）、CM営業の深さの誤読を修正。数値は過去資料から変わっている</li>
</ul>
<h2>お願いしたいこと</h2>
<ul>
<li>紹介元別の新規と終了理由の内訳の記録（新規不足の院から）→ 弱い紹介経路を特定</li>
<li>院別の医師FTEの最新値 → 医師1人あたり患者数・キャパ判定を更新</li>
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
