#!/usr/bin/env python3
"""ח1ג – מסמך אימות: docs/electrical/04-first-floor-riser.md (מתוך data/electrical/first-riser.json). הרצה: python3 tools/electrical/verify_first_riser.py"""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = json.load(open(os.path.join(ROOT, 'data/electrical/first-riser.json'), encoding='utf-8')); Lv = d['levels']; H0 = 280.5
br = '\n'.join(f"| {b['door']} | {b['doorName']} | {b['length_m']:.2f} | {', '.join(b['blockWalls']) or '—'} |" for b in d['branches'])
st = '\n'.join(f"| {s['n']} | {s['title']} | `{s['step']}` | {s['text']} |" for s in d['steps'])
ck = '\n'.join(f"| {c['ref']} | {c['clear_m']} | {c['required_m']} | {'תקין' if c['ok'] else '**נכשל**'} | {c['note']} |" for c in d['checks'])
f = lambda H: f"{H:.2f} ({H-H0:+.2f})"
doc = f"""# ח1ג – מעגלי קומה א' מהלוח הראשי: עלייה מעל הלוח וחלוקה בהנמכה (הצעה, 13.11.2026)

**מעמד:** הצעה לאישור אביחי. גובה ההנמכה זמני.
- נתונים: `data/electrical/first-riser.json`, נוצר ע"י `python3 tools/electrical/propose_first_riser.py` (קלט: `tools/electrical/first-riser-inputs.json`).
- מסמך זה: `python3 tools/electrical/verify_first_riser.py`.

**ההחלטה (אביחי, 13.11.2026):** {d['decision']}.

![העלייה מעל הלוח](screenshots/h1c-riser-niche.png)
![קומה א' – תוכנית החלל הטכני](screenshots/h1c-first-plan.png)
![במודל](screenshots/h1c-first-3d.png)

## 1. למה זה עובד (תיקון להסבר הקודם)

- **קורה B-25** יושבת בראש קיר הנישה, והפנים שלה מיושרים עם פני הקיר. צרור שעולה **לפני הקיר**, בתוך ארון הנגרות, עובר לידה בלי לחדור לקורה. היא חוסמת רק צנרת שעוברת בתוך הקיר.
- **מעל הנישה** יש את הרצפה FS2 ({f(Lv['fs2TopAbs'])}). החדירה דרכה היא בשרוולים ברצפה, לא בקורה. FS2 נמצא מתחת לתקרת הגג, כלומר בתוך הבית.
- מעל FS2 ומסביבו יש חלל (המדרגות והגובה הכפול). הצרור **ממשיך לעלות בחלל עד גובה החלל הטכני שמעל ההנמכה**, ושם עובר אל קומה א'.

## 2. מפלסים

| מה | רום | מקור |
|---|---|---|
| ראש הלוח הראשי | {f(Lv['panelTopAbs'])} | ח1 |
| רצפה FS2 (עליון / תחתון) | {f(Lv['fs2TopAbs'])} / {f(Lv['fs2BottomAbs'])} | K-31 |
| רצפה גמורה קומה א' | {f(Lv['firstFloorFinishAbs'])} | {Lv['firstFloorFinishSource']} |
| **הנמכת תקרה – זמני** | {f(Lv['droppedCeilingAbs'])} | {Lv['droppedCeiling']['note']} |
| תוואי הצרור | {f(Lv['routeAbs'])} | 12 ס"מ מתחת לתקרת הגג |
| תחתית תקרת הגג | {f(Lv['roofSoffitAbs'])} | K-41 |

## 3. התוואי

- **עלייה:** {d['riser']['height_m']:.2f} מ' מראש הלוח. {d['riser']['note']}.
- **צרור בחלל הטכני:** {d['trunk']['length_m']:.2f} מ' עד {d['distribution']['name']}. מתוכם **{d['trunk']['overVoid_m']:.2f} מ' מעל החלל**, ושם צריך סינר גבס. פתח בקיר בלוקים: {', '.join(d['trunk']['blockWalls'])}.
- **צנרת:** {d['bundle']['conduits']}. {d['bundle']['note']}.

| הסתעפות לדלת | חדר | אורך (מ') | פתחים בקירות בלוקים |
|---|---|---|---|
{br}

ההסתעפויות סכמטיות ומגיעות עד פנים החדר. החלוקה לנקודות בתוך כל חדר תיקבע בשלב הנקודות (ח4).

## 4. סדר הביצוע

| # | שלב | שלב במודל | מה עושים |
|---|---|---|---|
{st}

## 5. בדיקות

| בדיקה | ערך | נדרש | תוצאה | הערה |
|---|---|---|---|---|
{ck}

## 6. פתוח

| # | נושא |
|---|---|
| E20 | גובה הנמכת התקרה בקומה א' (זמני ‎+6.35, חלל טכני 30 ס"מ), ובאילו חדרים יש הנמכה |
| E21 | סינר גבס מעל החלל ({d['trunk']['overVoid_m']:.1f} מ') – לתאם עם העיצוב; ארון הנגרות של הלוח עד התקרה |
| E22 | שקעים בקומה א' יגיעו בירידות מהתקרה בתוך הקירות. לאשר שאין נקודות ברצפה |
"""
open(os.path.join(ROOT, 'docs/electrical/04-first-floor-riser.md'), 'w', encoding='utf-8').write(doc); print('docs/electrical/04-first-floor-riser.md')
