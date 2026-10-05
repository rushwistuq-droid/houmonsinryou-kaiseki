"""本部向け定型ダッシュボード（単一HTML）。"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .hq_analysis import HQPipelineResult


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def render_hq_dashboard(result: HQPipelineResult) -> str:
    """オフライン閲覧可能な単一HTMLを生成。"""
    clinics = result.clinics
    o = result.overlap
    actions = result.action_sheets or []

    clinic_rows = []
    for r in clinics:
        cap = f"{r.home_capture_pct:.1f}" if r.home_capture_pct is not None else "-"
        ah = f"{r.actual_home:.0f}" if r.actual_home is not None else "-"
        cls = {
            "above": "ok",
            "within": "mid",
            "below": "bad",
        }.get(r.capture_vs_band, "")
        clinic_rows.append(
            f"<tr class='{cls}'>"
            f"<td>{_esc(r.name)}</td>"
            f"<td>{_esc(r.density_tier)}</td>"
            f"<td>{r.home_visit_competitors}</td>"
            f"<td class='num'>{r.market_home:,.0f}</td>"
            f"<td class='num'>{r.exclusive_market_home:,.0f}</td>"
            f"<td>{r.expected_share_low_pct:g}–{r.expected_share_high_pct:g}</td>"
            f"<td class='num'>{ah}</td>"
            f"<td class='num'>{cap}</td>"
            f"<td>{_esc(r.capture_vs_band)}</td>"
            f"<td>{_esc(r.external_competition_tier)}</td>"
            f"</tr>"
        )

    sens_rows = []
    for s in result.sensitivity:
        def g(rad, key):
            v = s.by_radius.get(rad, {}).get(key, -1)
            if key == "home_capture_pct":
                return f"{v:.1f}" if v >= 0 else "-"
            return f"{v:,.0f}"

        sens_rows.append(
            "<tr>"
            f"<td>{_esc(s.name)}</td>"
            f"<td class='num'>{g('5','market_home')}</td><td class='num'>{g('5','home_capture_pct')}</td>"
            f"<td class='num'>{g('8','market_home')}</td><td class='num'>{g('8','home_capture_pct')}</td>"
            f"<td class='num'>{g('10','market_home')}</td><td class='num'>{g('10','home_capture_pct')}</td>"
            "</tr>"
        )

    fac_rows = []
    for f in result.facility_kpi:
        cf = f["contract_facility_patients"]
        ch = f["contract_home_patients"]
        sp = f["facility_share_of_panel_pct"]
        fac_rows.append(
            "<tr>"
            f"<td>{_esc(f['name'])}</td>"
            f"<td class='num'>{'-' if cf is None else f'{cf:.0f}'}</td>"
            f"<td class='num'>{'-' if ch is None else f'{ch:.0f}'}</td>"
            f"<td class='num'>{'-' if sp is None else f'{sp:.1f}'}</td>"
            f"<td class='num'>{f['market_facility_demand']:,.0f}</td>"
            "</tr>"
        )

    action_cards = []
    for a in actions:
        action_cards.append(
            "<article class='card'>"
            f"<h3>{_esc(a['clinic_name'])} "
            f"<span class='tag'>{_esc(a['decision'])}</span> "
            f"<span class='prio'>{_esc(a['priority'])}</span></h3>"
            f"<p>{_esc(a['rationale'])}</p>"
            "<div class='cols'>"
            "<div><h4>やる</h4><ul>"
            + "".join(f"<li>{_esc(x)}</li>" for x in a.get("actions") or [])
            + "</ul></div>"
            "<div><h4>KPI</h4><ul>"
            + "".join(f"<li>{_esc(x)}</li>" for x in a.get("kpis") or [])
            + "</ul></div>"
            "<div><h4>やらない</h4><ul>"
            + "".join(f"<li>{_esc(x)}</li>" for x in a.get("dont") or [])
            + "</ul></div>"
            "</div></article>"
        )

    data_json = html.escape(json.dumps(result.to_dict(), ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>わかさクリニック 本部ダッシュボード</title>
<style>
:root {{
  --bg: #f3f0e8;
  --ink: #1c2430;
  --muted: #5b6573;
  --line: #d5d0c4;
  --accent: #0f5c4c;
  --warn: #8a3b12;
  --ok: #1f6b3a;
  --bad: #8f1d1d;
  --card: #fffdf8;
  --serif: "Shippori Mincho", "Hiragino Mincho ProN", "Yu Mincho", serif;
  --sans: "IBM Plex Sans JP", "Hiragino Sans", "Noto Sans JP", sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; color: var(--ink); background:
    radial-gradient(1200px 600px at 10% -10%, #e7efe9 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 0%, #efe6d8 0%, transparent 50%),
    var(--bg);
  font-family: var(--sans); line-height: 1.55;
}}
header {{
  padding: 2.2rem 1.5rem 1.2rem; border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255,253,248,.9), rgba(255,253,248,.55));
}}
header h1 {{
  font-family: var(--serif); font-weight: 600; font-size: clamp(1.6rem, 3vw, 2.3rem);
  margin: 0 0 .4rem; letter-spacing: .02em; color: var(--accent);
}}
header p {{ margin: .2rem 0; color: var(--muted); max-width: 52rem; }}
main {{ padding: 1.2rem 1.5rem 3rem; display: grid; gap: 1.4rem; }}
section {{
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 1rem 1.1rem 1.2rem; box-shadow: 0 10px 30px rgba(28,36,48,.04);
}}
h2 {{ font-family: var(--serif); font-size: 1.25rem; margin: 0 0 .8rem; color: var(--accent); }}
h3 {{ margin: 0 0 .4rem; font-size: 1.05rem; }}
h4 {{ margin: .2rem 0; font-size: .85rem; color: var(--muted); letter-spacing: .04em; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .8rem; }}
.kpi {{
  padding: .85rem; border-radius: 12px; background: #f7f4ec; border: 1px solid var(--line);
}}
.kpi .label {{ font-size: .75rem; color: var(--muted); }}
.kpi .value {{ font-family: var(--serif); font-size: 1.35rem; margin-top: .15rem; }}
table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
th, td {{ padding: .45rem .4rem; border-bottom: 1px solid var(--line); text-align: left; }}
th {{ font-size: .75rem; color: var(--muted); font-weight: 600; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr.ok td:nth-child(9) {{ color: var(--ok); font-weight: 600; }}
tr.bad td:nth-child(9) {{ color: var(--bad); font-weight: 600; }}
tr.mid td:nth-child(9) {{ color: var(--muted); }}
.tag {{
  display: inline-block; padding: .1rem .45rem; border-radius: 999px;
  background: #e4efe9; color: var(--accent); font-size: .75rem; font-weight: 600;
}}
.prio {{ font-size: .75rem; color: var(--warn); }}
.card {{ border-top: 1px solid var(--line); padding: .9rem 0; }}
.card:first-child {{ border-top: 0; }}
.cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .6rem; }}
ul {{ margin: .2rem 0 0; padding-left: 1.1rem; }}
li {{ margin: .15rem 0; }}
.note {{ color: var(--muted); font-size: .85rem; }}
footer {{ padding: 0 1.5rem 2rem; color: var(--muted); font-size: .8rem; }}
@media (max-width: 720px) {{
  table {{ display: block; overflow-x: auto; }}
  header, main, footer {{ padding-left: 1rem; padding-right: 1rem; }}
}}
</style>
</head>
<body>
<header>
  <h1>わかさクリニック 本部ダッシュボード</h1>
  <p>市場規模・獲得率・排他的市場・外部競合・施設契約KPI・アクションシートを同一フォーマットで固定表示します。</p>
  <p class="note">標準半径 { _esc(result.radius_km_primary) } km ／ { _esc(result.radius_policy.get('rule','')) }</p>
</header>
<main>
  <section>
    <h2>サマリー</h2>
    <div class="kpis">
      <div class="kpi"><div class="label">ユニオン居宅市場</div><div class="value">{o.union_market_home:,.0f}</div></div>
      <div class="kpi"><div class="label">単純合算居宅市場</div><div class="value">{o.naive_sum_market_home:,.0f}</div></div>
      <div class="kpi"><div class="label">二重計上（65+）</div><div class="value">{o.overlap_pct_of_naive:.1f}%</div></div>
      <div class="kpi"><div class="label">対象院</div><div class="value">{len(clinics)}</div></div>
    </div>
  </section>

  <section>
    <h2>院別指標（標準 { _esc(result.radius_km_primary) } km）</h2>
    <table>
      <thead>
        <tr>
          <th>院</th><th>密度帯</th><th>在支診</th><th>市場居宅</th><th>排他居宅</th>
          <th>期待帯%</th><th>実績居宅</th><th>獲得率%</th><th>判定</th><th>外部競合</th>
        </tr>
      </thead>
      <tbody>
        {''.join(clinic_rows)}
      </tbody>
    </table>
    <p class="note">在支診は関東信越厚生局の届出受理名簿。座標は医療情報ネットと突合できた件数（下限）。施設は契約KPIで評価。</p>
  </section>

  <section>
    <h2>半径感度（5 / 8 / 10 km）</h2>
    <table>
      <thead>
        <tr>
          <th>院</th>
          <th>5km市場</th><th>5km獲得%</th>
          <th>8km市場</th><th>8km獲得%</th>
          <th>10km市場</th><th>10km獲得%</th>
        </tr>
      </thead>
      <tbody>{''.join(sens_rows)}</tbody>
    </table>
  </section>

  <section>
    <h2>施設契約KPI（市場需要と分離）</h2>
    <table>
      <thead>
        <tr><th>院</th><th>契約施設</th><th>契約居宅</th><th>施設/パネル%</th><th>施設市場需要（参考）</th></tr>
      </thead>
      <tbody>{''.join(fac_rows)}</tbody>
    </table>
  </section>

  <section>
    <h2>アクションシート</h2>
    {''.join(action_cards)}
  </section>
</main>
<footer>
  データ: 国勢調査メッシュ / NDB / 介護情報公表 / 医療情報ネット公開診療所。JSON埋め込みあり（検索用コメント）。
  <!-- HQ_JSON:{data_json} -->
</footer>
</body>
</html>
"""


def write_hq_dashboard(result: HQPipelineResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_hq_dashboard(result), encoding="utf-8")
    return path
