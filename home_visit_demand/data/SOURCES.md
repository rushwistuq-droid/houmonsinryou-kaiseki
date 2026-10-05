# 原本データの入手元

| データ | 出典 | 取得方法 |
|--------|------|----------|
| `ndb_home_age.xlsx` / `ndb_home_pref.xlsx` | 厚労省 第10回NDBオープンデータ C在宅医療 | https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177221_00014.html |
| `mesh_zips/NN.zip` | 令和2年国勢調査 地域メッシュ統計 T001102 | e-Stat GIS `statsId=T001102&code=NN` |
| `ipss_age_raw/NN.xlsx` | 社人研 地域別将来推計人口（令和5年推計）市区町村5歳階級 | https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities/ |
| `facilities_raw/jigyosho_*.csv` | 厚労省 介護サービス情報公表システム オープンデータ | https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html |
| `clinics_raw/*` / `competitors_home.csv.gz` | 厚労省 医療情報ネット オープンデータ（診療所） | https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html |
| `zaishishin_raw/*` / `zaishishin.csv.gz` | 関東信越厚生局 届出受理医療機関名簿（在宅療養支援診療所） | https://kouseikyoku.mhlw.go.jp/kantoshinetsu/chousa/kijyun.html |
| `pop2022_1.xlsx` | 総務省 人口推計 2022年10月1日 | https://www.stat.go.jp/data/jinsui/2022np/ |
| `munic_coords.json` | Wikidata SPARQL（P429+P625） | https://query.wikidata.org |

再生成: `python3 scripts/build_v2_datasets.py`
