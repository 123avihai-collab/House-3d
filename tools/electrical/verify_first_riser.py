#!/usr/bin/env python3
"""ח1ג – מסמך אימות: docs/electrical/04-first-floor-riser.md (מתוך data/electrical/first-riser.json). הרצה: python3 tools/electrical/verify_first_riser.py"""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = json.load(open(os.path.join(ROOT, 'data/electrical/first-riser.json'), encoding='utf-8')); Lv = d['levels']; H0 = 280.5
br = '\n'.join(f"| {b['door']} | {b['doorName']} | {b['length_m']:.2f} | {', '.join(b['blockWalls']) or '—'} |" for b in d['branches'])
st = '\n'.join(f"| {s['n']} | {s['title']} | `{s['step']}` | {s['text']} |" for s in d['steps'])
ck = '\n'.join(f"| {c['ref']} | {c['clear_m']} | {c['required_m']} | {'תקין' if c['ok'] else '**נכשל**'} | {c['note']} |" for c in d['checks'])
f = lambda H: f"{H:.2f} ({H-H0:+.2f})"
a = d.get('acReserve')
ac = (f"- **{a['name']}:** {a['size_m'][0]}×{a['size_m'][1]}×{a['size_m'][2]} מ', {a['fromBox_m']:.1f} מ' מתיבת החלוקה. תחתית {a['bottomAbs']:.2f}, ראש {a['topAbs']:.2f}, כלומר {a['aboveCeiling_m']*100:.0f} ס\"מ מעל ההנמכה. מרחק בתוכנית מצנרת החשמל: {a['clearFromTrays_m']:.2f} מ'.\n- {a['note']}\n- חשמל למזגן: {a['power']}") if a else '- לא נמצא מקום – לבדוק'
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
| **הנמכת תקרה – 35 ס"מ (ניתן לשינוי)** | {f(Lv['droppedCeilingAbs'])} | {Lv['droppedCeiling']['note']} |
| גובה נטו מתחת להנמכה | {Lv['netHeightUnderCeiling_m']:.2f} מ' | רצפה גמורה עד ההנמכה |
| רצפה גמורה עד התקרה היצוקה | {Lv['floorToSoffit_m']:.2f} מ' | ‎+3.85 עד תחתית תקרת הגג |
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

## 3א. מיני-מרכזי – מקום שמור

{ac}

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
| E20 | **הוחלט (13.11):** הנמכה 35 ס"מ, כמו בקרקע, ניתנת לשינוי (`depth_m` בקובץ הקלט). פתוח: באילו חדרים |
| E21 | סינר גבס מעל החלל ({d['trunk']['overVoid_m']:.1f} מ') – לתאם עם העיצוב; ארון הנגרות של הלוח עד התקרה |
| E22 | שקעים בקומה א' – בירידות מהתקרה בקירות; אין נקודות ברצפה (נבדק – החלוקה בהנמכה). שקע רצפה בודד – צינור ביציקת תקרת הקרקע |
| E3 | **הוחלט (13.11):** מיזוג מיני-מרכזי – נשמר נפח ליחידה הפנימית במסדרון (ראה סעיף 3) |
"""
open(os.path.join(ROOT, 'docs/electrical/04-first-floor-riser.md'), 'w', encoding='utf-8').write(doc); print('docs/electrical/04-first-floor-riser.md')
