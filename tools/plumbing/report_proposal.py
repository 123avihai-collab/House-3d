#!/usr/bin/env python3
"""Plumbing proposal -> docs/plumbing/03-proposal.md (tables for review with Avihai)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = json.load(open(os.path.join(ROOT, 'data/plumbing/proposal.json'), encoding='utf-8'))
H0 = json.load(open(os.path.join(ROOT, 'data/site/origin.json')))['H0']
rel = lambda H: f'{H - H0:+.2f}'
FL = {'ground': 'קרקע', 'first': "קומה א'", 'unit': 'מרתף', 'roof': 'גג', 'shaft': 'פיר'}
L = ['# הצעת תכנון – אינסטלציה (לאישור)', '',
     'נוצר ע"י `python3 tools/plumbing/propose.py` ו-`report_proposal.py`. **כל מה שכאן הוא הצעה**: מוצג במודל רק במצב "עם ההצעה" (שכבות → אינסטלציה), ודורש את אישורך ואחר כך את אישור היועץ. ערכים טיפוסיים (גבהים, קטרים, בידוד) מסומנים ב-`tools/plumbing/proposal-inputs.json`.', '',
     '## החלטות שעליהן ההצעה בנויה', '']
L += [f'- **{d["id"]}** ({d["date"]}): {d["text"]}' for d in P['decisions']]
L += ['', '## לא בהצעה – ממתין להחלטה', ''] + [f'- **{d["id"]}**: {d["text"]}' for d in P['pending']]
L += ['', '## 1. הזזת קולטנים מתוך הבטון', '', '| צ.א | חוצה במיקום של היועץ | הזזה | בצירי הבית (מזרח / צפון, ס"מ) | אחרי ההזזה | מרחק לקו קיר | ענפים שהוארכו |', '|---|---|---|---|---|---|---|']
for s in P['stackMoves']:
    if not s.get('pts3d'): continue
    L.append(f'| {s["stack"]} | {", ".join(s["clashesBefore"])} | {s["displacement_m"] * 100:.0f} ס"מ | {s["local_dxdy_m"][0] * 100:+.0f} / {s["local_dxdy_m"][1] * 100:+.0f} | '
             f'{"נקי" if not s["clashesAfter"] else ", ".join(s["clashesAfter"])} | {s["distToWall_m"] * 100:.0f} ס"מ | {len(s["connectors"])} |')
L += ['', 'החיפוש: המקום הפנוי הקרוב ביותר (רשת של 2 ס"מ, עד 90 ס"מ), עם מרווח 3 ס"מ מכל אלמנט בטון לכל גובה הקולטן, מחוץ לממ"ד ולפיר, 16 ס"מ לפחות מקולטן או צמ"ג אחר, ועם העדפה להישאר צמוד לקו קיר (להלבשה). '
      'הענפים של היועץ הוארכו אופקית אל המיקום החדש, באותו מפלס. **לבדוק:** הלבשה / קיר בכל מיקום (אדריכל), ושמיקום הקורות במודל הוא בקירוב (עד IFC).', '']
sh = P['shaft']
L += ['## 2. פיר אינסטלציה (החלטה D2)', '', f'- מידות נטו: {sh["local"][2] * 100:.0f}×{sh["local"][3] * 100:.0f} ס"מ, בין {rel(sh["bottom"])} ל-{rel(sh["top"])}, צמוד לפאה הצפונית של הממ"ד ומחוץ לו.',
      f'- בדיקת שלד: {"לא חוצה קירות, עמודים או קורות שבמודל" if not sh["clashes"] else ", ".join(sh["clashes"])}. תקרת הגג (K-41) עוד לא במודל – לבדוק בשלב 3ד.',
      '- בפיר: עולה מים קרים (ברז ראשי בגובה +0.30 בקומת הקרקע), עולה לקומה א\', ירידה למוני היחידות, אספקה חמה וקו סחרור מבודדים.',
      '- במרתף הפיר נוחת בחדר הרחצה של יחידה 2 שבסקיצה. הכיור של יחידה 2 הוזז לאורך הקיר.', '']
L += ['## 3. מחלקים', '', '| מחלק | קומה | יציאות מים קרים | יציאות מים חמים | הערה |', '|---|---|---|---|---|']
for m in P['manifolds']:
    L.append(f'| {m["title"]} | {FL[m["floor"]]} | {len(m["outlets"]["cold"])} | {"ממתין PD1" if m["hotPending"] else len(m["outlets"]["hot"])} | ברז כדורי לכל יציאה, ברז ראשי בכניסה |')
L += ['', '## 4. נקודות מים (גבהים טיפוסיים – לאישור)', '', '| קבועה | קומה | גובה מעל הריצוף | PEX | קרים | חמים |', '|---|---|---|---|---|---|']
for p in P['points']:
    L.append(f'| {p["title"]} – {p["fixture"]} | {FL[p["floor"]]} | {p["H_rel"]:.2f} | ø{p["D_mm"]} | {"✓" if p["cold"] else ""} | {"✓" if p["hot"] else ("ממתין PD1" if p["hotPending"] else "")} |')
runs = P['runs']
L += ['', '## 5. צנרת', '', f'- {len(runs)} קטעים, סה"כ {sum(r["length_m"] for r in runs):.0f} מ\' PEX. כל צינור בשרוול מריכף לכל אורכו (הערה 10). אספקה חמה וחזרה – בבידוד {next(r["insulation_mm"] for r in runs if r.get("insulation_mm"))} מ"מ (זמני).',
      f'- הקטע הארוך ביותר ממחלק לנקודה: {max(r["length_m"] for r in runs if r["from"].startswith("MAN-") and r["to"] != "RET-RISER"):.1f} מ\' (הערה 3 בפרט הסחרור: עד 15 מ\') ✓',
      '- תוואי: בתוך מילוי הרצפה (‎−0.07 מתחת לריצוף), סביב קירות ובפתחים. מעבר בבטון אסור; הממ"ד אסור בקרקע. עלייה בקיר לכל נקודה.', '',
      '| קטע | מערכת | קומה | קוטר | אורך | מ → אל |', '|---|---|---|---|---|---|']
SYS = {'cold': 'קרים', 'hot': 'חמים', 'return': 'סחרור'}
for r in runs:
    if not r['from'].startswith('MAN-'): L.append(f'| {r["id"]} | {SYS[r["system"]]} | {FL[r["floor"]]} | ø{r["D_mm"]} | {r["length_m"]:.1f} | {r["from"]} → {r["to"]} |')
L += ['', f'(ועוד {sum(1 for r in runs if r["from"].startswith("MAN-"))} קווים ממחלקים לנקודות – בטבלה בממשק, בלחיצה על כל קו.)', '']
L += ['## 6. שרוולים ומעברים', '', '| # | מעבר | קומה | צינור | שרוול | ITM / רום |', '|---|---|---|---|---|---|']
for i, s in enumerate(P['sleeves'], 1):
    L.append(f'| {i} | {s["through"]} | {FL.get(s["floor"], s["floor"])} | {s["pipe"]} | {s["sleeve"]} | {s["at"][0]:.2f} / {s["at"][1]:.2f} · {rel(s["at"][2])} |')
L += ['', '## 7. מה מוחלף מתוכנית היועץ (מוסתר במצב "עם ההצעה")', '', ', '.join(f'`{x}`' for x in P['superseded']), '',
      'קווי המים של היועץ שנכנסו לקירות (סוף תכנון), העולה WJ23 שבתוך העמוד C8, קו המטבח מהחצר, הקו החם בגג למחלק הקודם, ו-6 הקולטנים במיקום הקודם.', '']
open(os.path.join(ROOT, 'docs/plumbing/03-proposal.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('ok', len(L))
