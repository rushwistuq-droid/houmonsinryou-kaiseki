#!/usr/bin/env python3
"""
機密オペレーションデータ × 地域データ 統合分析
confidential/operational_data.yaml を読み込み（Git管理外）
"""

import math
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

# 地域分析モジュールを再利用
sys.path.insert(0, str(Path(__file__).parent))
from wakasa_clinic_regional_analysis import CLINICS, calculate_catchment_metrics, RADIUS_KM

CONF_DIR = Path(__file__).parent / "confidential"
DATA_FILE = CONF_DIR / "operational_data.yaml"
OPENING_DATES_FILE = Path(__file__).parent / "clinic_opening_dates.yaml"
OUTPUT_FILE = CONF_DIR / "performance_report.txt"


def load_opening_dates():
    with open(OPENING_DATES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def opening_year(key: str, meta: dict) -> int:
    raw = meta.get(key, {}).get("開設", "")
    if isinstance(raw, int):
        return raw
    s = str(raw)
    return int(s[:4]) if s else 0


def strategic_era(key: str, eras: dict) -> str:
    for era, info in eras.items():
        if key in info.get("branches", []):
            return era
    return "未分類"


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else 0.0

# 分析用の院名マッピング
CLINIC_KEY_MAP = {
    "01": "本院", "02": "所沢", "03": "ひばりが丘", "04": "石神井公園",
    "05": "三鷹", "06": "府中", "07": "調布", "08": "三軒茶屋",
    "09": "津田沼", "10": "西日暮里", "11": "高円寺", "12": "リーフシティ市川",
}


def load_ops():
    with open(DATA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def analyze():
    ops = load_ops()
    opening_meta = load_opening_dates()
    eras = opening_meta.get("strategic_eras", {})
    physicians = ops["physicians_fte"]
    patients = ops["patients"]
    w_home = ops["revenue_weight"]["home"]
    w_fac = ops["revenue_weight"]["facility"]

    rows = []
    regional = {}

    for clinic in CLINICS:
        if clinic.id == "13":
            continue
        key = CLINIC_KEY_MAP.get(clinic.id)
        if not key or key not in patients:
            continue

        reg = calculate_catchment_metrics(clinic)
        regional[key] = reg

        p = patients[key]
        home, fac = p["home"], p["facility"]
        total = home + fac
        fac_ratio = fac / total * 100 if total else 0

        fte = physicians.get(key)
        if fte is None:
            raise ValueError(f"医師数未設定: {key}")
        fte_note = ""

        weighted = home * w_home + fac * w_fac
        rev_index_per_fte = weighted / fte if fte else 0
        patients_per_fte = total / fte if fte else 0
        home_per_fte = home / fte if fte else 0

        est_demand = reg["estimated_home_patients"]
        # 施設患者は地域推計に含まれないため、居宅のみでシェア算出
        home_share = home / est_demand * 100 if est_demand else 0
        total_share = total / est_demand * 100 if est_demand else 0

        theoretical = reg["theoretical_share_per_clinic"]
        effort_index = total / theoretical * 100 if theoretical else 0

        # 競合調整後効率 = 実患者/理論枠 を医師数で割った相対値
        efficiency_vs_market = (total / max(theoretical, 1)) / fte * 100

        # 地域難易度（競合密度ベース、0-100）
        comp_density = reg["home_support_per_100k_elderly"]
        regional_difficulty = min(100, comp_density / 65 * 60 + reg["wakasa_overlap_count"] * 4)

        # 努力補正スコア = 効率指数 / 地域難易度（高いほど地域以上に成果）
        performance_score = efficiency_vs_market / max(regional_difficulty, 10) * 100

        rows.append({
            "key": key,
            "home": home, "facility": fac, "total": total,
            "fac_ratio": fac_ratio,
            "fte": fte,
            "fte_used": fte,
            "fte_note": fte_note,
            "weighted": weighted,
            "rev_index_per_fte": rev_index_per_fte,
            "patients_per_fte": patients_per_fte,
            "home_per_fte": home_per_fte,
            "home_share": home_share,
            "total_share": total_share,
            "theoretical": theoretical,
            "effort_index": effort_index,
            "efficiency_vs_market": efficiency_vs_market,
            "regional_difficulty": regional_difficulty,
            "performance_score": performance_score,
            "comp_density": comp_density,
            "overlap": reg["wakasa_overlap_count"],
            "elderly": reg["total_elderly_65"],
            # 地域・競合指標
            "hospitals": reg["hospitals"],
            "home_support_clinics": reg["home_support_clinics"],
            "home_support_hospitals": reg["home_support_hospitals"],
            "visit_clinics_est": reg["visit_clinics_est"],
            "visit_hospitals_est": reg["visit_hospitals_est"],
            "residential_facilities": reg["residential_facilities"],
            "residential_beds": reg["residential_beds"],
            "nursing_facilities": reg["nursing_facilities_all"],
            "visit_clinics_per_100k": reg["visit_clinics_per_100k_elderly"],
            "visit_hospitals_per_100k": reg["visit_hospitals_per_100k_elderly"],
            "residential_fac_per_100k": reg["residential_fac_per_100k_elderly"],
            "residential_beds_per_100k": reg["residential_beds_per_100k_elderly"],
            "expected_fac_ratio": None,
            "fac_ratio_gap": None,
            "opening_year": opening_year(key, opening_meta),
            "strategic_era": strategic_era(key, eras),
            "years_open": 2026 - opening_year(key, opening_meta) if opening_year(key, opening_meta) else None,
        })

    # 浦和（地域分析に未登録のため簡易）
    if "浦和針ヶ谷" in patients:
        p = patients["浦和針ヶ谷"]
        home, fac = p["home"], p["facility"]
        total = home + fac
        fte = physicians.get("浦和針ヶ谷", 1.0)
        weighted = home * w_home + fac * w_fac
        rows.append({
            "key": "浦和針ヶ谷",
            "home": home, "facility": fac, "total": total,
            "fac_ratio": fac / total * 100 if total else 100,
            "fte": fte, "fte_used": fte, "fte_note": "（地域推計未実装・新規院）",
            "weighted": weighted,
            "rev_index_per_fte": weighted / fte,
            "patients_per_fte": total / fte,
            "home_per_fte": home / fte,
            "home_share": None, "total_share": None,
            "theoretical": None,
            "effort_index": None,
            "efficiency_vs_market": None,
            "regional_difficulty": None,
            "performance_score": None,
            "comp_density": None,
            "overlap": None,
            "elderly": None,
        })

    # 地域施設密度と施設患者比率の相関分析
    analyzed = [r for r in rows if r.get("residential_fac_per_100k") is not None]
    if len(analyzed) >= 3:
        fac_ratios = [r["fac_ratio"] for r in analyzed]
        res_fac_d = [r["residential_fac_per_100k"] for r in analyzed]
        res_bed_d = [r["residential_beds_per_100k"] for r in analyzed]
        visit_hosp_d = [r["visit_hospitals_per_100k"] for r in analyzed]

        corr_fac_res = pearson(fac_ratios, res_fac_d)
        corr_fac_beds = pearson(fac_ratios, res_bed_d)
        corr_fac_vhosp = pearson(fac_ratios, visit_hosp_d)

        # 入所定員ベースの期待施設患者比率（粗い推計）
        group_fac_ratio = sum(r["facility"] for r in analyzed) / sum(r["total"] for r in analyzed) * 100
        for r in analyzed:
            # 地域の入所系施設密度が高いほど施設患者が増える構造を正規化
            avg_bed = sum(res_bed_d) / len(res_bed_d)
            r["expected_fac_ratio"] = min(95, max(15, group_fac_ratio * (r["residential_beds_per_100k"] / avg_bed)))
            r["fac_ratio_gap"] = r["fac_ratio"] - r["expected_fac_ratio"]

    rows.sort(key=lambda x: x.get("performance_score") or 0, reverse=True)

    lines = []
    lines.append("=" * 100)
    lines.append("【機密】わかさクリニックグループ 実績×地域 統合分析")
    lines.append(f"前提: 半径{RADIUS_KM}km圏 / 収益代理: 居宅×{w_home} + 施設×{w_fac}")
    lines.append("=" * 100)
    lines.append("")

    # サマリー
    hdr = f"{'院名':<14} {'居宅':>6} {'施設':>6} {'計':>6} {'施設%':>6} {'医師':>5} {'患者/医師':>8} {'収益指数/医師':>12} {'居宅シェア':>8} {'努力指数':>8} {'成果スコア':>8}"
    lines.append(hdr)
    lines.append("-" * 100)

    group_home = group_fac = group_total = group_weighted = group_fte = 0
    for r in rows:
        fte_disp = f"{r['fte']:.1f}"
        share_disp = f"{r['home_share']:.1f}%" if r['home_share'] is not None else "  n/a"
        effort_disp = f"{r['effort_index']:.0f}" if r['effort_index'] is not None else "  n/a"
        perf_disp = f"{r['performance_score']:.0f}" if r['performance_score'] is not None else "  n/a"
        lines.append(
            f"{r['key']:<14} {r['home']:>6} {r['facility']:>6} {r['total']:>6} "
            f"{r['fac_ratio']:>5.0f}% {fte_disp:>5} {r['patients_per_fte']:>8.0f} "
            f"{r['rev_index_per_fte']:>12.0f} {share_disp:>8} {effort_disp:>8} {perf_disp:>8}"
        )
        if r['fte'] is not None and r['key'] != '浦和針ヶ谷':
            group_home += r['home']
            group_fac += r['facility']
            group_total += r['total']
            group_weighted += r['weighted']
            group_fte += r['fte']

    lines.append("-" * 100)
    lines.append(
        f"{'合計(浦和除く)':<14} {group_home:>6} {group_fac:>6} {group_total:>6} "
        f"{group_fac/group_total*100:>5.0f}% {group_fte:>5.0f} {group_total/group_fte:>8.0f} "
        f"{group_weighted/group_fte:>12.0f}"
    )
    lines.append("")

    # === 開院時期・戦略世代分析 ===
    lines.append("=" * 100)
    lines.append("■ 開院時期と居宅/施設ミックス（公式開院日ベース）")
    lines.append("-" * 100)
    lines.append(
        f"  {'院名':<14} {'開院':>8} {'戦略世代':<12} {'施設%':>6} {'居宅%':>6} "
        f"{'収益指数':>8} {'解釈'}"
    )
    lines.append("-" * 100)
    era_groups = {}
    for r in sorted(analyzed, key=lambda x: x["opening_year"]):
        era = r["strategic_era"]
        era_groups.setdefault(era, []).append(r["fac_ratio"])
        note = ""
        if era == "施設重視期":
            note = "施設契約蓄積型"
        elif r["key"] in ("府中", "調布"):
            note = "転換期第1弾・居宅寄り"
        elif r["key"] == "津田沼":
            note = "居宅最優先モデル"
        elif r["key"] == "三軒茶屋":
            note = "事業譲渡・施設継承"
        elif r["key"] in ("リーフシティ市川", "浦和針ヶ谷"):
            note = "オウカス併設・立ち上げ期"
        lines.append(
            f"  {r['key']:<14} {r['opening_year']:>8} {era:<12} "
            f"{r['fac_ratio']:>5.0f}% {100-r['fac_ratio']:>5.0f}% "
            f"{r['rev_index_per_fte']:>8.0f} {note}"
        )
    lines.append("")
    for era, ratios in era_groups.items():
        avg = sum(ratios) / len(ratios)
        lines.append(f"  【{era}】平均施設患者比率: {avg:.0f}%（{len(ratios)}院）")
    if len(analyzed) >= 3:
        years = [r["opening_year"] for r in analyzed]
        facs = [r["fac_ratio"] for r in analyzed]
        corr_year_fac = pearson(years, facs)
        lines.append(f"  開院年と施設患者%の相関: r = {corr_year_fac:+.2f}")
        if corr_year_fac < -0.4:
            lines.append("  → 新しい院ほど居宅比重が高い傾向（ご指摘の戦略転換と一致）")
        elif corr_year_fac > 0.4:
            lines.append("  → 開院が新しい院ほど施設比率が高い（地域・譲渡等の影響が大きい）")
    lines.append("")
    lines.append("  主要マイルストーン:")
    lines.append("  ・2000年 本院開設 / 2014年 在宅医療部門開設（施設診療の蓄積期）")
    lines.append("  ・2021-2022年 所沢・石神井・ひばりが丘・三鷹（多摩拡大・施設重視モデル）")
    lines.append("  ・2023年4月 府中・調布開院＝令和5年度診療報酬改定と同月・居宅重視へ転換")
    lines.append("  ・2024年4月 津田沼（居宅71%）/ 2025-2026年 23区・千葉・浦和の拡大")
    lines.append("")

    # === 競合・病院・施設密度分析 ===
    lines.append("=" * 100)
    lines.append("■ 地域競合環境（8km圏内推計）")
    lines.append("-" * 100)
    chdr = (
        f"{'院名':<14} {'病院':>5} {'訪問実施':>8} {'在宅支援':>8} {'訪問診療':>8} "
        f"{'入所施設':>8} {'入所定員':>8} {'訪問診/10万':>10} {'入所施設/10万':>12}"
    )
    lines.append(chdr)
    lines.append("-" * 100)
    for r in sorted(analyzed, key=lambda x: x["visit_clinics_est"], reverse=True):
        lines.append(
            f"{r['key']:<14} {r['hospitals']:>5} {r['visit_hospitals_est']:>8} "
            f"{r['home_support_clinics']:>8} {r['visit_clinics_est']:>8} "
            f"{r['residential_facilities']:>8.0f} {r['residential_beds']:>8.0f} "
            f"{r['visit_clinics_per_100k']:>10.0f} {r['residential_fac_per_100k']:>12.0f}"
        )
    lines.append("  ※訪問実施病院=在宅支援病院+一般病院×25% / 訪問診療=一般診療所×20.5%（厚労省推計）")
    lines.append("  ※在宅支援=在宅療養支援診療所（直接競合） / 入所施設=入所型+特定施設（JMAP）")
    lines.append("")

    lines.append("■ 地域施設密度と施設患者比率の関係")
    if len(analyzed) >= 3:
        lines.append(f"  相関係数（施設患者% vs 入所施設密度/10万高齢者）: r = {corr_fac_res:+.2f}")
        lines.append(f"  相関係数（施設患者% vs 入所定員/10万高齢者）    : r = {corr_fac_beds:+.2f}")
        lines.append(f"  相関係数（施設患者% vs 訪問実施病院/10万高齢者）: r = {corr_fac_vhosp:+.2f}")
        lines.append("")
        if corr_fac_beds >= 0.5:
            lines.append("  → 入所系施設が多い地域ほど施設患者比率が高くなる傾向が強い（地域構造が患者ミックスを規定）")
        elif corr_fac_beds >= 0.3:
            lines.append("  → 施設患者比率は地域の入所施設密度と正の相関あり。院間差の一部は地域で説明可能")
        else:
            lines.append("  → 施設密度だけでは説明しきれない差あり。営業戦略・施設契約の差が影響")
        lines.append("")

        lines.append(f"  {'院名':<14} {'実施設%':>8} {'期待施設%':>10} {'差(実-期)':>10} {'入所定員/10万':>12} 解釈")
        lines.append("  " + "-" * 78)
        for r in sorted(analyzed, key=lambda x: x.get("fac_ratio_gap") or 0, reverse=True):
            gap = r.get("fac_ratio_gap")
            if gap is None:
                continue
            if gap > 10:
                note = "地域より施設偏重（施設営業が強い）"
            elif gap < -10:
                note = "地域より居宅偏重（施設余地あり or 獲得弱）"
            else:
                note = "地域構造と整合"
            lines.append(
                f"  {r['key']:<14} {r['fac_ratio']:>7.0f}% {r['expected_fac_ratio']:>9.0f}% "
                f"{gap:>+9.0f}pt {r['residential_beds_per_100k']:>12.0f} {note}"
            )
        lines.append("")

    lines.append("■ ライバル訪問診療クリニック密度と獲得の関係")
    for r in sorted(analyzed, key=lambda x: x["home_share"] or 0, reverse=True):
        lines.append(
            f"  {r['key']}: 在宅支援診{r['home_support_clinics']} / 訪問診療推計{r['visit_clinics_est']} / "
            f"居宅シェア{r['home_share']:.1f}% / 施設{r['fac_ratio']:.0f}%"
        )
    lines.append("")

    # 解釈セクション
    lines.append("■ 指標の読み方")
    lines.append("  収益指数/医師 = 居宅×1.0 + 施設×0.4 を医師常勤で割った相対値（売上の代理指標）")
    lines.append("  居宅シェア = 当院居宅患者数 ÷ 8km圏推定居宅需要（高齢者×4.5%）")
    lines.append("  努力指数 = 実患者合計 ÷ 理論獲得枠 ×100（100超=地域平均以上の獲得）")
    lines.append("  成果スコア = 市場効率を地域難易度で補正（高い=地域以上に好成績）")
    lines.append("")

    # ランキング
    ranked = [r for r in rows if r['performance_score'] is not None]
    ranked.sort(key=lambda x: x['rev_index_per_fte'], reverse=True)

    lines.append("■ 医師1人あたり収益指数ランキング（施設/居宅構成反映）")
    for i, r in enumerate(ranked, 1):
        lines.append(f"  {i:2}. {r['key']}: {r['rev_index_per_fte']:.0f} （患者{r['patients_per_fte']:.0f}/医師, 施設{r['fac_ratio']:.0f}%）")
    lines.append("")

    # 地域 vs 努力の判定
    lines.append("■ 地域性 vs 努力の判定")
    for r in sorted([x for x in rows if x['performance_score']], key=lambda x: x['performance_score'], reverse=True):
        if r['performance_score'] >= 120:
            verdict = "★地域以上の高成果（努力・体制が機能）"
        elif r['performance_score'] >= 80:
            verdict = "○地域並み（適正）"
        elif r['effort_index'] and r['effort_index'] >= 100:
            verdict = "△患者数は確保も効率面で課題"
        else:
            verdict = "×地域要因＋獲得不足の両面"
        lines.append(f"  {r['key']}: 成果スコア{r['performance_score']:.0f} / 努力指数{r['effort_index']:.0f} → {verdict}")
    lines.append("")

    # 施設偏重分析
    lines.append("■ 施設偏重院の収益構造")
    fac_heavy = sorted([r for r in rows if r['total'] > 0], key=lambda x: x['fac_ratio'], reverse=True)
    for r in fac_heavy[:5]:
        lines.append(
            f"  {r['key']}: 施設{r['fac_ratio']:.0f}% → "
            f"患者数は{r['total']}人だが収益指数は{r['rev_index_per_fte']:.0f}/医師 "
            f"（居宅{r['home']}人換算で同等収益なら施設寄与は{r['facility']}×{w_fac}≈{r['facility']*w_fac:.0f}）"
        )
    lines.append("")

    # 本部向け提言
    lines.append("■ 本部評価への提言（実績データ反映）")
    lines.append("  1. 本院は施設69%・患者1,660人/医師6名 → 数量最大だが収益指数は施設ミックスで要精査")
    lines.append("  2. 所沢・津田沼は居宅シェア・居宅比重が高く収益効率が良い院")
    lines.append("  3. 西日暮里・市川は医師1名体制で母数小。市川は居宅57%と収益構造は比較的良好")
    lines.append("  4. 高円寺は施設68%・医師1名 → 三軒茶屋より施設偏重で収益指数は低め")
    lines.append("  5. 調布は居宅54%・患者325人/1.5医師 → 居宅比重が高く収益効率は多摩で上位")
    lines.append("")

    report = "\n".join(lines)
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[機密] レポート保存: {OUTPUT_FILE}")
    return rows


if __name__ == "__main__":
    analyze()
