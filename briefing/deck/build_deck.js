// 理事長面談スライドを生成する（機密: 出力は analysis/confidential/briefing/ のみ）
//   python3 briefing/build_all.py && python3 briefing/deck/export_deck_data.py
//   NODE_PATH=<pptxgenjs の node_modules> node briefing/deck/build_deck.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const CONF = path.join(ROOT, "analysis/confidential/briefing");
const PUB = path.join(ROOT, "briefing/output");
const D = JSON.parse(fs.readFileSync(path.join(CONF, "deck_data.json"), "utf8"));
const OUT = path.join(CONF, "わかさ_理事長面談資料_2026-10.pptx");
const APPLY_THEME = process.env.PPTX_APPLY_THEME;

const THEME = {
  name: "Wakasa Briefing",
  headFontFace: "Yu Gothic",
  bodyFontFace: "Yu Gothic",
  colors: {
    dk1: "1A1A1A", lt1: "FFFFFF", dk2: "0F2D4A", lt2: "EEF3F8",
    accent1: "2A78D6", accent2: "EB6834", accent3: "1BAF7A", accent4: "0D366B",
    accent5: "8A8985", accent6: "CDE2FB", hlink: "2A78D6", folHlink: "4A3AA7",
  },
};
const HEX = THEME.colors;
const W = 13.333, H = 7.5, MX = 0.6;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "訪問診療データ分析のご報告";
pres.author = "わかさクリニックグループ";
const C = pres.SchemeColor;
const ym = (m) => { const [y, mo] = m.split("-"); return `${y}年${Number(mo)}月`; };
const FOOTER = D.monthly && D.monthly.last_month
  ? `機密｜わかさクリニックグループ 理事長面談資料｜2026年10月（実績は${ym(D.monthly.last_month)}末時点）`
  : "機密｜わかさクリニックグループ 理事長面談資料｜2026年10月（実績は2026年7月時点）";

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.2, w: 11.5, h: 1.6, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.0, w: 11.5, h: 1.6, fontSize: 18, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CLOSING",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.8, w: 11.5, h: 1.0, fontSize: 36, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent6 },
});
pres.defineSlideMaster({
  title: "SECTION",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.6, w: 11.5, h: 1.2, fontSize: 36, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.0, w: 11.5, h: 1.2, fontSize: 16, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent6 },
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: W - 2 * MX, h: 0.85, fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOTER, options: { x: MX, y: H - 0.45, w: 10, h: 0.3, fontSize: 10, color: HEX.accent5, margin: 0 } } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent5 },
});

let section = "";
function content(title, sectionTitle) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sectionTitle || section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function sectionSlide(title, sub) {
  section = title;
  pres.addSection({ title });
  const s = pres.addSlide({ masterName: "SECTION", sectionTitle: title });
  s.addText(title, { placeholder: "title" });
  if (sub) s.addText(sub, { placeholder: "body" });
  return s;
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, fontSize: 14, color: C.text1, margin: 0, valign: "top" }, o));
}
function card(s, x, y, w, h, name, fill) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || C.background2 }, line: { type: "none" }, rectRadius: 0.08, objectName: name });
}
function bullets(items, o) {
  return items.map((t, i) => ({ text: t, options: Object.assign({ bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 }, o || {}) }));
}
function img(s, file, x, y, maxW, maxH, pxW, pxH, name) {
  const r = pxW / pxH;
  let w = maxW, h = maxW / r;
  if (h > maxH) { h = maxH; w = maxH * r; }
  s.addImage({ path: file, x, y, w, h, objectName: name });
  return { w, h };
}
const fmt = (n) => Math.round(n).toLocaleString("ja-JP");
const pct = (x) => `${Math.round(x * 100)}%`;
const clinics = D.clinics;
const byId = Object.fromEntries(clinics.map((c) => [c.id, c]));
const judged = clinics.filter((c) => c.months >= 12 && c.id !== "honin");
const tight = clinics.filter((c) => c.per_fte >= 250);
const maxPen = Math.max(...judged.map((c) => c.penetration));
const coef = D.model.coef;
const loo = D.model.loo_error_pct / 100;
const eraPct = Math.round((1 - Math.exp(coef.d_facility_era)) * 100);
const fitted = clinics.filter((c) => c.months >= 6 && c.id !== "honin");
const inBand = fitted.filter((c) => c.perf <= 1 + loo && c.perf >= 1 / (1 + loo)).length;
const above = fitted.filter((c) => c.perf >= 1.15).map((c) => c.name);
const screenErr = (label) => Math.round(100 * D.screen.find((r) => r["モデル"].startsWith(label))["予測誤差(LOO)"]);
const M = D.monthly || null;
const stalled = clinics.filter((c) => c.verdict.startsWith("停滞"));
const stalledFull = stalled.filter((c) => c.penetration >= 0.8);  // 自院エリアは上位院並みに取り込み済み
const stalledRoom = stalled.filter((c) => c.penetration < 0.8);   // エリア内に余地あり
const names = (arr) => arr.map((c) => c.name).join("・");

// ---------------------------------------------------------------- 1. 表紙
pres.addSection({ title: "表紙" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "表紙" });
  s.addText("訪問診療データ分析のご報告", { placeholder: "title" });
  s.addText([
    { text: "患者獲得の予測指数と、各院の運営・出店への活用", options: { breakLine: true } },
    { text: "2026年10月　理事長面談資料（機密）", options: { fontSize: 14 } },
  ], { placeholder: "body" });
}

// ---------------------------------------------------------------- 2. 要旨
pres.addSection({ title: "要旨" });
{
  const s = content("本日お伝えしたいこと：伸びは居宅に移った。止まっている院の課題は担当エリアの狭さと居宅獲得の仕組み", "要旨");
  const r2 = Math.round(D.model.r2 * 100);
  const items = M ? [
    [`${(M.home_last / M.home_first).toFixed(1)}倍`, `グループの居宅患者は${ym(M.first_month)}の${fmt(M.home_first)}人から${fmt(M.home_last)}人へ。施設は2025年春から横ばい`],
    [`${r2}%`, "院ごとの居宅患者数の差は「年数」「地域の未充足度」「立ち上げ方針」の3つで説明できる"],
    [`${stalled.length}院`, `居宅が直近6か月伸びていない院（${names(stalled)}）`],
    [`${stalledFull.length}院`, `うち${names(stalledFull)}は、自院の担当エリアを同条件の上位院並みに取り込み済み。伸ばすにはエリアの再設定が必要`],
  ] : [
    [`${r2}%`, "院ごとの居宅患者数の差は「在宅開始からの年数」「地域の未充足度」「立ち上げ方針」の3つで説明できる"],
    ["約3倍", "在宅医療がまだ行き渡っていない埼玉・千葉では、同じ年数でも東京の約3倍伸びる"],
    [`${stalled.length}院`, "居宅が伸びていない院"],
    [`${stalledFull.length}院`, "担当エリアを上位院並みに取り込み済みの院"],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4;
  items.forEach(([big, label], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.55, cw, 3.3, `要旨カード${i + 1}`);
    txt(s, big, { x: x + 0.3, y: 1.85, w: cw - 0.6, h: 1.0, fontSize: 40, bold: true, color: i >= 2 ? C.accent2 : C.accent1, fontFace: "Yu Gothic" });
    txt(s, label, { x: x + 0.3, y: 3.0, w: cw - 0.6, h: 1.75, fontSize: 14 });
  });
  txt(s, "ご提案", { x: MX, y: 5.2, w: 2, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    `停滞院は2つに分けて対応：エリアを取り切りつつある院（${names(stalledFull)}）は担当エリアの再設定・隣接地域の開拓、エリア内に余地がある院（${names(stalledRoom)}）は紹介経路の強化`,
    `施設を抑える方針の下では、施設型で立ち上げた院ほど居宅の獲得の仕組みづくりが急務（施設重視期に開院した院は同条件で居宅が約${eraPct}%少ない）`,
    "次の出店は埼玉東部・千葉北西部を軸に。浦和は立ち上げが基準を下回っており、早期の支援が必要",
  ]), { x: MX, y: 5.55, w: W - 2 * MX, h: 1.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

// ---------------------------------------------------------------- 3. データ
sectionSlide("1. 現在保有しているデータ", "公的統計11種＋院内データ。信頼度と、まだ無いデータも合わせて整理しました");
{
  const s = content("保有データの全体像：公的統計で「需要」「競合」「連携先」を、院内実績で「成果」を測っている");
  const cols = [
    ["需要（どれだけ患者が生まれるか）", C.accent1, ["国勢調査 250mメッシュ人口（2020）", "社人研 将来推計人口（〜2050）", "NDB 在宅医療の受療率（年齢・県別）", "NDB 居宅/施設の比率", "総務省 人口推計"]],
    ["競合・連携先（誰と取り合い、誰と組むか）", C.accent1, ["厚生局 在支診・在支病名簿（2026-08）全件の位置", "医療施設調査（2023）", "介護施設 7,790か所・定員40万人", "CM事業所 10,601か所", "訪問看護 5,208か所"]],
    ["院内（機密）", C.accent2, ["院別 月次患者数（2023-12〜2026-09、居宅・施設・がん医総）", "院別 医師FTE（2026-07）", "開院日・立ち上げ時期", "補正イベント（移管・報告値修正、確認済み）"]],
    ["まだ無いデータ（院内）", C.accent5, ["新規・終了患者数（記録様式を用意）", "紹介元別の新規患者数（同上）", "施設の契約リスト"]],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4;
  cols.forEach(([head, col, items], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.5, cw, 4.6, `データ区分${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.8, w: 0.32, h: 0.32, fill: { color: col }, line: { type: "none" }, objectName: `区分マーク${i + 1}` });
    txt(s, head, { x: x + 0.75, y: 1.75, w: cw - 1.0, h: 0.75, fontSize: 15, bold: true, color: C.text2 });
    s.addText(bullets(items), { x: x + 0.3, y: 2.65, w: cw - 0.55, h: 3.3, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  txt(s, "詳細（出典・時点・格納場所・信頼度）は付録「01 データカタログ」。生データは Excel（wakasa_briefing_data.xlsx）でもご覧いただけます", { x: MX, y: 6.35, w: W - 2 * MX, h: 0.5, fontSize: 12, color: C.accent5 });
}
{
  const s = content("これまでの指数を整理し、公式に使う指数を絞りました");
  const cols = [
    ["公式に使う", C.accent1, ["未充足度（潜在÷顕在の居宅需要）", "年数・地域補正後の実力", "到達目安・到達率", "排他率（グループ重複の少なさ）", "実効競合・競合密度", "居宅比率・医師1人あたり患者数（増員の目安）", "立地スコア・3年後予測"]],
    ["参考に見る", C.accent5, ["顕在居宅需要（旧・居宅市場規模）", "居宅獲得率", "公平シェアKPI・実務KPI", "収益指数（施設0.4換算）", "ユニオン市場"]],
    ["使わない", C.accent2, ["努力指数・成果スコア（手入力の人口に誤り）", "推定居宅需要＝高齢者×4.5%", "期待獲得率帯（閾値に根拠がない）", "CM拠点あたり居宅数（CM数が概数）"]],
  ];
  const cw = (W - 2 * MX - 2 * 0.3) / 3;
  cols.forEach(([head, col, items], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.5, cw, 4.75, `指数区分${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.8, w: 0.32, h: 0.32, fill: { color: col }, line: { type: "none" }, objectName: `指数マーク${i + 1}` });
    txt(s, head, { x: x + 0.75, y: 1.75, w: cw - 1, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    s.addText(bullets(items), { x: x + 0.3, y: 2.45, w: cw - 0.55, h: 3.7, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  txt(s, "定義と判断理由は付録「02 指数辞書」", { x: MX, y: 6.45, w: W - 2 * MX, h: 0.4, fontSize: 12, color: C.accent5 });
}
{
  const s = content("検証の過程で過去の分析の誤りを6点見つけ、すべて修正しました");
  const rows = [
    ["自治体データ（手入力）の誤り", "57件中20件が公式推計と10〜15%超ずれ（入間市の人口が半分など）", "公的原典ベースに一本化"],
    ["院の位置のずれ", "本院3.8km・三鷹2.4km・所沢1.3km・市川1.2km", "国土地理院の住所検索に差し替え"],
    ["機能強化型の判定漏れ", "名簿の全角数字を読めず、全件「従来型」扱い", "判定を修正し自動テストを追加"],
    ["県境での需要のずれ", "圏全体に1県の受療率を適用（本院・所沢・市川で±20〜60%）", "メッシュごとに所在県の率を適用"],
    ["競合の座標欠落", "在支診の36%に位置情報なし", "名簿突合＋国土地理院で100%に"],
    ["CM営業の深さの誤読", "ひばりが丘のCMあたり居宅は府中・調布の半分とされていた", "自院担当エリアで比べると同水準"],
  ];
  const head = ["問題", "影響", "対応"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } }));
  s.addTable([head, ...rows.map((r) => r.map((t) => ({ text: t })))], {
    x: MX, y: 1.55, w: W - 2 * MX, colW: [3.0, 5.6, 3.53], fontSize: 14, color: HEX.dk1,
    border: { type: "solid", pt: 0.75, color: "D9DEE5" }, rowH: 0.58, valign: "middle", margin: 0.08, fontFace: "Yu Gothic",
  });
  txt(s, "結果として、院ごとの市場規模や獲得率の数字は過去資料から変わっています。今後は本資料の数値を基準とします", { x: MX, y: 5.95, w: W - 2 * MX, h: 0.6, fontSize: 15, color: C.text2, bold: true });
}

// ---------------------------------------------------------------- 4. 予測指数
sectionSlide("2. 患者獲得の予測指数", "13種類の候補を、12院の実績で比べました");
{
  const s = content("「人が多い所」ではなく「まだ取られていない所」が伸びる：未充足度が最も効く指数");
  const sc = D.screen;
  const labels = sc.map((r) => r["モデル"].replace("【採用】", "（採用）"));
  const vals = sc.map((r) => Math.round(r["予測誤差(LOO)"] * 100));
  const colors = sc.map((r) => (r["モデル"].includes("採用") ? HEX.accent2 : r["モデル"].includes("未充足度") ? HEX.accent1 : "9EC5F4"));
  s.addChart(pres.charts.BAR, [{ name: "予測誤差(%)", labels: labels.slice().reverse(), values: vals.slice().reverse() }], {
    x: MX, y: 1.4, w: 7.6, h: 5.4, barDir: "bar", chartColors: colors.slice().reverse(),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 11, dataLabelColor: HEX.dk1,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMaxVal: 90, valAxisMinVal: 0,
    showLegend: false, showTitle: true, title: "1院ずつ抜いて予測したときの誤差（小さいほど良い）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt",
    barGapWidthPct: 40,
  });
  const x = 8.6;
  card(s, x, 1.5, W - MX - x, 5.25, "比較の読み方");
  txt(s, "読み方", { x: x + 0.3, y: 1.75, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "高齢者数・需要・競合の「量」は、多いほど居宅が少ない（都会度を測っているだけ）",
    `未充足度を加えると誤差が±${screenErr("月数のみ")}%→±${screenErr("月数＋未充足度")}%に縮小`,
    `さらに立ち上げ方針（開院時期）を加えると±${Math.round(D.model.loo_error_pct)}%、R²=${D.model.r2.toFixed(2)}`,
    `施設重視期に開院した院は、同じ条件で居宅が約${eraPct}%少ない`,
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.3, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content(`予測モデルの当てはまり：${fitted.length}院中${inBand}院が誤差±${Math.round(D.model.loo_error_pct)}%の帯に入る`);
  const im = img(s, path.join(CONF, "figures/slide/fig_model_fit.png"), MX, 1.35, 7.4, 5.5, 1720, 1280, "モデル当てはまり図");
  const x = MX + im.w + 0.4;
  card(s, x, 1.5, W - MX - x, 5.25, "モデル説明");
  txt(s, "モデルの中身", { x: x + 0.3, y: 1.75, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    `年数が2倍になると居宅は約${Math.pow(2, coef.b_months).toFixed(1)}倍`,
    `未充足度2.0の地域は1.0の地域の約${Math.pow(2, coef.c_underserved).toFixed(1)}倍`,
    `施設重視期に開院した院は約${eraPct}%少ない`,
    above.length ? `斜線より大きく上の院（${above.join("・")}）は、地域と年数の割に多く取れている` : "斜線から大きく外れる院はない",
    "2024年6月〜2026年9月の各四半期の実績で推定し直しても、係数はほぼ同じ（安定）",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("有用な患者獲得予測指数として、次の5つを採用します");
  const rows = [
    ["1", "未充足度", "潜在居宅需要（東京都並みに普及した場合）÷ 現在の居宅需要", "出店地の選定・既存院の伸びしろ"],
    ["2", "在宅開始からの月数", "同じ地域条件なら、月数でおおむね伸び方が決まる", "立ち上げ基準カーブ"],
    ["3", "立ち上げ方針（開院時期）", "居宅重視で立ち上げた院は約1.8倍", "新規院はすべて居宅重視で"],
    ["4", "排他率", "圏内高齢者のうち、自院が一番近い人の割合", "出店時の食い合いチェック・役割分担"],
    ["5", "競合密度", "75歳以上1万人あたりの実効競合（機能強化型を重く）", "都内の候補比較・停滞要因（競合過密）の判定"],
  ];
  rows.forEach(([n, name, def, use], i) => {
    const y = 1.5 + i * 1.0;
    s.addShape(pres.shapes.OVAL, { x: MX, y: y + 0.1, w: 0.6, h: 0.6, fill: { color: i < 3 ? C.accent1 : C.accent6 }, line: { type: "none" }, objectName: `番号${n}` });
    txt(s, n, { x: MX, y: y + 0.1, w: 0.6, h: 0.6, fontSize: 18, bold: true, color: i < 3 ? C.background1 : C.text2, align: "center", valign: "middle" });
    txt(s, name, { x: MX + 0.9, y: y + 0.12, w: 3.2, h: 0.55, fontSize: 18, bold: true, color: C.text2, valign: "middle" });
    txt(s, def, { x: MX + 4.2, y: y + 0.12, w: 5.0, h: 0.6, fontSize: 14, valign: "middle" });
    txt(s, use, { x: MX + 9.4, y: y + 0.12, w: W - 2 * MX - 9.4, h: 0.6, fontSize: 14, color: C.accent1, bold: true, valign: "middle" });
  });
}

// ---------------------------------------------------------------- 5. 既存院
sectionSlide("3. 既存院の診断", "上限に近いのか、まだ伸ばせるのか（月次推移を含めた判定）");
{
  const s = content(M ? `院別の診断（${ym(M.last_month)}）：${stalled.length}院が停滞。主な課題は担当エリアの狭さと居宅獲得の仕組み` : "院別の診断：判定できる院はすべて「伸長余地あり」、課題は院ごとに異なる");
  const head = ["院", "在宅\n月数", "居宅", "施設", "居宅比", "地域\nタイプ", "実力", "上位院比", "判定"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 }, align: "center" } }));
  const body = clinics.map((c) => {
    const warnMix = c.home_mix < 0.3;
    const perfCol = c.months < 6 ? HEX.dk1 : c.perf >= 1.15 ? HEX.accent1 : c.perf <= 0.85 ? HEX.accent2 : HEX.dk1;
    const verdictShort = c.verdict.replace("（月次推移で判定）", "").replace("（判定保留）", "");
    return [
      { text: c.name, options: { bold: true } },
      { text: String(c.months), options: { align: "right" } },
      { text: fmt(c.home), options: { align: "right" } },
      { text: fmt(c.facility), options: { align: "right" } },
      { text: pct(c.home_mix), options: { align: "right", color: warnMix ? HEX.accent2 : HEX.dk1, bold: warnMix } },
      { text: c.area_type, options: { align: "center" } },
      { text: c.months >= 6 ? c.perf.toFixed(2) : "—", options: { align: "right", color: perfCol, bold: perfCol !== HEX.dk1 } },
      { text: c.id === "honin" ? "先行者" : c.months >= 12 ? pct(c.penetration) : "—", options: { align: "right" } },
      { text: verdictShort },
    ];
  });
  s.addTable([head, ...body], {
    x: MX, y: 1.35, w: W - 2 * MX, colW: [1.55, 0.8, 0.85, 0.85, 0.9, 1.0, 0.8, 0.9, 4.48],
    fontSize: 12, color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "D9DEE5" }, rowH: 0.34, valign: "middle", margin: [0.02, 0.08, 0.02, 0.08], fontFace: "Yu Gothic",
  });
  txt(s, "実力＝実績÷モデル期待値（1.15以上を青、0.85以下を橙）／上位院比＝自院が最寄りの潜在居宅需要の取り込み率を、同じ地域タイプの上位2院の平均と比べた値／橙字＝居宅比30%未満。本院は先行者のため比較対象外。在宅月数は本院2014-04・所沢2021-06を仮置き", { x: MX, y: 6.35, w: W - 2 * MX, h: 0.6, fontSize: 11, color: C.accent5 });
}
{
  const s = content("同じ条件の上位院と比べると、停滞院は「担当エリアを取り切りつつある院」と「エリア内に余地がある院」に分かれる");
  const im = img(s, path.join(CONF, "figures/slide/fig_saturation.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "到達目安図");
  const x = MX + im.w + 0.35;
  card(s, x, 1.5, W - MX - x, 5.25, "上位院比の説明");
  txt(s, "上位院比とは", { x: x + 0.25, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "自院が最寄りの潜在居宅需要のうち、何%を居宅患者にできているかを、同じ地域タイプの上位院と比べた値",
    `上位院：都市型は${D.peer.都市型.members.join("・")}（約${(100 * D.peer.都市型.share).toFixed(0)}%）、未充足型は${D.peer.未充足型.members.join("・")}（約${(100 * D.peer.未充足型.share).toFixed(0)}%）`,
    "本院は地域で最初に訪問診療を始めた先行者のため比較対象外（上位院の約2.7倍）",
    "上位院も伸び続けているため、100%は上限ではなく「いまの上位水準」",
  ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("医師1人あたり患者数は「次の増員の時期」の目安（医師は患者に合わせて増やすため、伸び悩みの原因ではない）");
  const sorted = clinics.slice().sort((a, b) => b.per_fte - a.per_fte);
  s.addChart(pres.charts.BAR, [{ name: "医師1人あたり患者数", labels: sorted.map((c) => c.name), values: sorted.map((c) => Math.round(c.per_fte)) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (c.per_fte >= 250 ? HEX.accent2 : HEX.accent1)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 350,
    showLegend: false, showTitle: true, title: "医師1人（常勤換算）あたり患者数（居宅＋施設）　橙＝増員検討の目安（250人以上）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "医師数の扱い");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "医師は患者の増加に合わせて増やす運用のため、医師数は患者の伸びの「結果」。停滞の原因の判定には使わない",
    `250人を超えた院（${names(tight)}）は次の増員を検討する時期の目安`,
    "医師FTEは2026年7月時点。最新値で更新する",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("多摩〜区西部の4院は、圏内の半分以上で別のわかさ院のほうが近い：役割分担が論点");
  const sorted = clinics.slice().sort((a, b) => a.exclusive_ratio - b.exclusive_ratio);
  s.addChart(pres.charts.BAR, [{ name: "排他率", labels: sorted.map((c) => c.name), values: sorted.map((c) => Math.round(c.exclusive_ratio * 100)) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (c.exclusive_ratio < 0.5 ? HEX.accent2 : HEX.accent1)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 110,
    showLegend: false, showTitle: true, title: "排他率：8km圏の高齢者のうち自院が一番近い人の割合（橙＝50%未満）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "重複の示唆");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "同じCM事業所に複数院が営業する重複を解消する",
    "最寄り院の地図をもとに新規受付・営業の担当エリアを決める",
    "空いた営業資源を未開拓エリア（例：ひばりが丘北側の東久留米・清瀬）へ",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

{
  const s = content("CM営業の深さは、自院担当エリアで比べると多摩3院（ひばりが丘・府中・調布）は同水準");
  const sorted = clinics.filter((c) => c.months >= 12).slice().sort((a, b) => b.home_per_cm - a.home_per_cm);
  s.addChart(pres.charts.BAR, [{ name: "CM1か所あたり居宅", labels: sorted.map((c) => c.name), values: sorted.map((c) => c.home_per_cm) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (["hibarigaoka", "fuchu", "chofu"].includes(c.id) ? HEX.accent2 : HEX.accent1)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0,
    showLegend: false, showTitle: true, title: "自院が最寄りのCM事業所1か所あたりの居宅患者（開院12か月以上）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "CM営業の示唆");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  const hb = byId.hibarigaoka, mt = byId.mitaka, kj = byId.koenji;
  s.addText(bullets([
    "8km圏のCM全体で割ると、ひばりが丘は府中の約半分に見える。しかし圏内CMの多くは他のわかさ院のほうが近い",
    `担当CMのうち他院と重なる割合：ひばりが丘${pct(hb.cm_contested_share)}・三鷹${pct(mt.cm_contested_share)}・高円寺${pct(kj.cm_contested_share)}`,
    "院別の営業先リスト（CM・訪問看護、係争の印つき）を作成済み",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

// ---------------------------------------------------------------- 月次推移
if (M) {
  sectionSlide("4. 月次推移で見えたこと", `${ym(M.first_month)}〜${ym(M.last_month)}の院別月次データ`);
  {
    const s = content(`グループ全体：居宅は${(M.home_last / M.home_first).toFixed(1)}倍に。施設は2025年春から横ばいで、伸びはすべて居宅`);
    const im = img(s, path.join(CONF, "figures/slide/fig_m_group_trend.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "グループ推移図");
    const x = MX + im.w + 0.35;
    card(s, x, 1.5, W - MX - x, 5.25, "グループ推移の要点");
    txt(s, "要点", { x: x + 0.25, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
    s.addText(bullets([
      `総患者 ${fmt(M.total_first)}人 → ${fmt(M.total_last)}人`,
      `居宅比 ${pct(M.mix_first)} → ${pct(M.mix_last)}`,
      `直近12か月：居宅 +${fmt(M.home_last - M.home_12m_ago)}人、施設 ${M.fac_last - M.fac_12m_ago >= 0 ? "+" : ""}${fmt(M.fac_last - M.fac_12m_ago)}人`,
      `施設は2025年3月 ${fmt(M.fac_2025_03)}人 → ${ym(M.last_month)} ${fmt(M.fac_last)}人（${M.fac_last >= M.fac_2025_03 ? "+" : ""}${fmt(M.fac_last - M.fac_2025_03)}人）`,
    ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  }
  {
    const s = content("院別の推移：伸び続ける院と、1年以上横ばいの院がはっきり分かれる");
    img(s, path.join(CONF, "figures/slide/fig_m_clinics.png"), MX + 0.6, 1.2, W - 2 * MX - 1.2, 5.75, 2400, 1720, "院別推移図");
  }
  {
    const s = content("停滞している院：担当エリアを取り切りつつある院と、エリア内に余地がある院で打ち手が異なる");
    const head = ["院", "居宅", "12か月の\n増減", "直近6か月\n（人/月）", "排他率", "競合密度", "上位院比", "主因の候補 → 打ち手"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 }, align: "center" } }));
    const body = stalled.map((c) => {
      const m = M.clinics[c.name];
      const cause = `${c.cause} → ${c.action}`;
      return [
        { text: c.name, options: { bold: true } },
        { text: fmt(c.home), options: { align: "right" } },
        { text: `${m.home_chg_12m >= 0 ? "+" : ""}${m.home_chg_12m}`, options: { align: "right" } },
        { text: `${m.home_slope_6m >= 0 ? "+" : ""}${m.home_slope_6m}`, options: { align: "right" } },
        { text: pct(c.exclusive_ratio), options: { align: "right", color: c.exclusive_ratio < 0.5 ? HEX.accent2 : HEX.dk1, bold: c.exclusive_ratio < 0.5 } },
        { text: c.competition_density.toFixed(1), options: { align: "right", color: c.competition_density >= 9 ? HEX.accent2 : HEX.dk1, bold: c.competition_density >= 9 } },
        { text: pct(c.penetration), options: { align: "right", bold: c.penetration >= 0.8 } },
        { text: cause },
      ];
    });
    s.addTable([head, ...body], {
      x: MX, y: 1.45, w: W - 2 * MX, colW: [1.5, 0.8, 1.0, 1.1, 0.85, 0.95, 0.95, 4.98],
      fontSize: 13, color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "D9DEE5" }, rowH: 0.55, valign: "middle", margin: [0.03, 0.08, 0.03, 0.08], fontFace: "Yu Gothic",
    });
    txt(s, "判定: 直近6か月の居宅の傾きが統計的に0と区別できない、またはS字カーブで頭打ち。上位院比80%以上＝担当エリアを取り切りつつある。排他率50%未満＝他院との重複、競合密度9以上＝競合過密（橙字）", { x: MX, y: 5.1, w: W - 2 * MX, h: 0.6, fontSize: 12, color: C.accent5 });
    txt(s, "施設を抑える方針の下で、施設型で立ち上げた院の居宅の伸びが止まっている。エリアの再設定と紹介経路づくりが打ち手", { x: MX, y: 5.8, w: W - 2 * MX, h: 0.6, fontSize: 15, bold: true, color: C.text2 });
  }
  {
    const s = content("データの補正（確認済み）：移管と報告値の修正を除いた「実態ベース」で分析しています");
    const tr = (M.transfers || [])[0];
    const rows = [
      ["2025年4月", tr ? `施設 ${tr["減少"]}（計${tr["減少合計"]}人）を高円寺へ移管` : "施設の移管", "移管（確認済み）。移管元の過去の施設数を移管分だけ差し引き、自然増減だけを評価"],
      ["2025年8月", "調布・府中・三軒茶屋・石神井公園・三鷹で施設・居宅が同時に減少", "少しずつずれていた報告値を実態に修正（確認済み）。ずれは徐々に積み上がったとみなし、過去の値を按分して補正"],
      ["2025年4月〜2026年1月", `本院の施設 ${M.clinics["本院"].facility_from_peak}人（ピーク比）`, "契約終了とカウント見直しが混在し分離できないため、補正せずそのまま"],
      ["2026年4月", "居宅にがん医総を含める集計に変更", "全院・全期間を「総数−施設」（がん医総を含む居宅）で統一。市川も同じ定義に揃えた"],
    ];
    const head = ["時期", "データの動き", "扱い"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } }));
    s.addTable([head, ...rows.map((r) => r.map((t) => ({ text: t })))], {
      x: MX, y: 1.5, w: W - 2 * MX, colW: [2.3, 4.9, 4.93], fontSize: 14, color: HEX.dk1,
      border: { type: "solid", pt: 0.75, color: "D9DEE5" }, rowH: 0.8, valign: "middle", margin: 0.08, fontFace: "Yu Gothic",
    });
    txt(s, "補正しても直近6〜12か月の判定（停滞5院）は変わらない。補正で変わるのはピークからの落ち幅と過去の推移", { x: MX, y: 5.8, w: W - 2 * MX, h: 0.5, fontSize: 15, bold: true, color: C.text2 });
  }
  {
    const s = content(`新しい院の立ち上げ：西日暮里・市川は基準どおり、浦和は未充足度${byId.urawa.underserved.toFixed(1)}の割に伸びが遅い`);
    const im = img(s, path.join(CONF, "figures/slide/fig_m_launch.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "立ち上げ実績図");
    const x = MX + im.w + 0.35;
    card(s, x, 1.5, W - MX - x, 5.25, "立ち上げの要点");
    txt(s, "要点と運用ルール案", { x: x + 0.25, y: 1.75, w: 3.5, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
    s.addText(bullets([
      "津田沼は最初の1年で基準を大きく上回り、その後は基準どおり",
      `浦和は${byId.urawa.months}か月で${byId.urawa.home}人。地域条件（未充足度${byId.urawa.underserved.toFixed(1)}）からの基準の約${Math.round(100 * byId.urawa.perf)}%`,
      "3・6・12か月で基準の70%未満なら本部が立ち上げ支援に入る",
    ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  }
  {
    const s = content("12か月後（2027年9月）の居宅の見通し：施策を変えなければ停滞院は横ばいのまま");
    const im = img(s, path.join(CONF, "figures/slide/fig_m_forecast.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "見通し図");
    const x = MX + im.w + 0.35;
    const sumLow = Object.values(M.clinics).reduce((a, c) => a + c.fc_low, 0);
    const sumHigh = Object.values(M.clinics).reduce((a, c) => a + c.fc_high, 0);
    card(s, x, 1.5, W - MX - x, 5.25, "見通しの要点");
    txt(s, "要点", { x: x + 0.25, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
    s.addText(bullets([
      `グループの居宅は ${fmt(M.home_last)}人 → ${fmt(sumLow)}〜${fmt(sumHigh)}人`,
      "伸びの大半は津田沼・西日暮里・高円寺・市川・浦和の新しい院",
      `エリア内に余地がある停滞院（${names(stalledRoom)}）が上位院並みになれば、さらに約${fmt(stalledRoom.reduce((a, c) => a + Math.max(0, c.reach_target - c.home), 0))}人の上積み余地`,
    ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  }
}

// ---------------------------------------------------------------- 6. 出店
sectionSlide("5. 出店と立ち上げ", "どこに出すと伸びるか、出した後に順調かをどう判定するか");
{
  const s = content("在宅医療の未充足度：埼玉・千葉は東京都並みに普及した場合の2倍超の需要が眠っている");
  img(s, path.join(CONF, "figures/slide/fig_map_underserved.png"), MX + 0.4, 1.25, W - 2 * MX - 0.8, 5.7, 2000, 1440, "未充足度マップ");
}
{
  const s = content("10年後の需要：郊外ほど高齢化が速く、85歳以上は本院・津田沼周辺で約1.5倍に");
  const sorted = clinics.slice().sort((a, b) => b.e85_growth_25_35 - a.e85_growth_25_35);
  s.addChart(pres.charts.BAR, [{ name: "85歳以上の伸び", labels: sorted.map((c) => c.name), values: sorted.map((c) => Math.round((c.e85_growth_25_35 - 1) * 100)) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (c.pref === "東京都" ? HEX.accent1 : HEX.accent2)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '"+"0"%"', dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 70,
    showLegend: false, showTitle: true, title: "8km圏の85歳以上人口の増加率 2025→2035（青＝東京都、橙＝埼玉・千葉）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "将来需要の示唆");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "居宅需要の中心は85歳以上。どの院の圏域も10年で2〜6割増える",
    "埼玉・千葉の院は平均+48%、都内の院は平均+29%と、郊外ほど速く増える",
    "出店スコアにも「10年後の伸び」を2割反映した",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("出店候補：上位は埼玉東部〜千葉北西部、既存院から16km以上離れ、10年で需要も大きく伸びる");
  img(s, path.join(CONF, "figures/slide/fig_map_site_score.png"), MX, 1.25, W - 2 * MX, 5.75, 2520, 1440, "立地スコアマップ");
}
// ---------------------------------------------------------------- 7. 活用提案
sectionSlide("6. 活用のご提案", "データを意思決定の道具として定着させる");
{
  const s = content("このデータで、評価・出店・人員配置・立ち上げ管理を同じ物差しで判断できるようになります");
  const items = [
    ["院の公平な評価", "「実力」指数を四半期の評価会議の最初の資料に"],
    ["出店先の選定", "候補住所を入れれば3年後予測と食い合いを即比較"],
    ["立ち上げ管理", "月次データと基準カーブで3・6・12か月に判定（浦和から）"],
    ["担当エリアの再設定", "上位院並みに取り込んだ院はエリアの再設定・隣接地域の開拓"],
    ["多摩の役割分担", "最寄り院の地図で営業エリアを決める"],
    ["居宅への構成転換", "施設偏重院は新規居宅を月次目標に"],
    ["紹介経路の診断", "新規・終了・紹介元の記録を始めれば3か月で弱い経路を特定"],
    ["10年後の需要", "85歳以上の将来推計で院ごとの需要増を先読み"],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4, ch = 2.35;
  items.forEach(([head, body], i) => {
    const x = MX + (i % 4) * (cw + 0.3), y = 1.45 + Math.floor(i / 4) * (ch + 0.3);
    card(s, x, y, cw, ch, `活用${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fill: { color: i !== 6 ? C.accent1 : C.accent5 }, line: { type: "none" }, objectName: `活用番号${i + 1}` });
    txt(s, String(i + 1), { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, head, { x: x + 0.95, y: y + 0.3, w: cw - 1.2, h: 0.5, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
    txt(s, body, { x: x + 0.3, y: y + 1.0, w: cw - 0.6, h: ch - 1.2, fontSize: 14 });
  });
}
pres.addSection({ title: "お願いと次のステップ" });
{
  const s = pres.addSlide({ masterName: "CLOSING", sectionTitle: "お願いと次のステップ" });
  s.addText("お願いしたいことと次のステップ", { placeholder: "title" });
  const asks = [
    ["新規・終了・紹介元の月次記録を開始", "停滞院の原因（紹介不足か終了増か）を3か月で特定"],
    ["院別の医師FTEの最新値", "増員時期の目安を更新"],
    ["出店候補物件の住所", "その場で3年後予測・食い合いを比較"],
    ["評価会議での「実力」指数の試行", "四半期ごとに更新（再計算は約40秒）"],
  ];
  asks.forEach(([a, b], i) => {
    const y = 2.3 + i * 0.95;
    s.addShape(pres.shapes.OVAL, { x: MX, y: y + 0.08, w: 0.42, h: 0.42, fill: { color: C.accent2 }, line: { type: "none" }, objectName: `お願い${i + 1}` });
    txt(s, String(i + 1), { x: MX, y: y + 0.08, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, a, { x: MX + 0.65, y: y + 0.05, w: 5.4, h: 0.5, fontSize: 18, bold: true, color: C.background1, valign: "middle" });
    txt(s, `→ ${b}`, { x: MX + 6.2, y: y + 0.05, w: 6.0, h: 0.5, fontSize: 16, color: C.accent6, valign: "middle" });
  });
  txt(s, "いただいたデータは機密として院内環境でのみ扱い、共有リポジトリには保存しません", { x: MX, y: 6.2, w: 11.5, h: 0.4, fontSize: 14, color: C.accent6 });
}

pres.writeFile({ fileName: OUT }).then(async (f) => {
  if (APPLY_THEME) {
    const { applyTheme } = require(APPLY_THEME);
    await applyTheme(f, THEME);
  }
  console.log(f);
});
