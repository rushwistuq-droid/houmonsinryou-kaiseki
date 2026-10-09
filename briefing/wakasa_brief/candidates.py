"""具体的な出店候補（駅・物件）の評価と、開院後の見込み（機密の候補リストを入力に使う）。

見込みは3本で示す:
  - モデル: 獲得予測モデル（月数・未充足度・転換期型）。商圏の大きさは入っていない
  - 頭打ちの目安: 新院が最寄りになる潜在居宅需要 × 津田沼の現在の取り込み率（未充足型で最も進んだ院）
  - 慎重: モデル × 最近開院した未充足型の院（市川）の実力
標準＝min(モデル, 頭打ちの目安)、慎重＝min(モデル×慎重係数, 頭打ちの目安)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Clinic, Engine
from .site_score import SiteScorer, add_scores

MONTHS = (6, 12, 24, 36)


def evaluate_candidates(engine: Engine, model, bench, diag: pd.DataFrame, grid: pd.DataFrame, cands: list[dict]) -> pd.DataFrame:
    S = SiteScorer(engine, model, bench)
    d = diag.set_index("name") if "name" in diag.columns else diag
    ref = d.loc["津田沼"]
    ref_share = float(ref.home / ref.exclusive_latent_home)
    cautious = float(d.loc["市川", "performance_index"]) if "市川" in d.index else 0.6
    rows = []
    base_excl = engine.exclusive_share()
    for c in cands:
        r = S.evaluate(c["lat"], c["lon"])
        allg = pd.concat([grid, pd.DataFrame([r])[[k for k in grid.columns if k in r]]], ignore_index=True)
        sc = add_scores(allg, engine)
        score = float(sc.score.iloc[-1])
        rank = int((sc.score > score).sum()) + 1
        # 既存院への影響（新院を加えたときの排他率の低下）
        cl = engine.clinics + [Clinic(id="cand", name=c["name"], lat=c["lat"], lon=c["lon"], pref="", home_start="2027-04", era="転換期")]
        ex = Engine(clinics=cl, radius_km=engine.radius_km)
        for k in ("mesh", "competitors", "cm_offices", "nursing", "future", "facilities", "munis"):
            if k in engine.__dict__:
                ex.__dict__[k] = engine.__dict__[k]
        ex_share = ex.exclusive_share()
        hit = [f"{o.name} {base_excl[o.id]['exclusive_ratio']:.0%}→{ex_share[o.id]['exclusive_ratio']:.0%}"
               for o in engine.clinics if base_excl[o.id]["exclusive_ratio"] - ex_share[o.id]["exclusive_ratio"] > 0.005]
        excl_latent = r["latent_home"] * r["exclusive_ratio_new"]
        plateau = excl_latent * ref_share
        row = {
            "name": c["name"], "label": c.get("label", c["name"]), "lat": c["lat"], "lon": c["lon"],
            "score": score, "rank": rank, "n_grid": len(sc),
            **{k: r[k] for k in ("elderly_65", "elderly_75", "market_home", "latent_home", "underserved_ratio", "competitors_n",
                                 "competitors_enhanced_n", "competition_density", "facility_residents", "exclusive_ratio_new",
                                 "reach_target", "e85_growth_25_35", "latent_home_2035", "cm_offices_n", "nursing_n",
                                 "nearest_clinic", "nearest_clinic_km", "underserved_extrapolated")},
            "plateau_tsudanuma_share": plateau, "ref_share": ref_share, "cautious_factor": cautious,
            "plateau_2035": plateau * r["latent_home_2035"] / r["latent_home"] if r["latent_home"] else np.nan,
            "overlap_effect": "、".join(hit) if hit else "なし",
        }
        for m in MONTHS:
            p = float(model.predict(m, r["underserved_ratio"], False))
            row[f"model_{m}"] = p
            row[f"std_{m}"] = min(p, plateau)
            row[f"low_{m}"] = min(p * cautious, plateau)
        rows.append(row)
    return pd.DataFrame(rows)
