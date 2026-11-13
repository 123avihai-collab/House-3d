#!/usr/bin/env python3
"""ח4 קומה א' – מסמך: docs/electrical/05-first-floor-points.md (מתוך data/electrical/points-first.json). הרצה: python3 tools/electrical/verify_points_first.py"""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = json.load(open(os.path.join(ROOT, 'data/electrical/points-first.json'), encoding='utf-8')); Hh = d['heights']
cnt = '\n'.join(f"| {room} | " + ' · '.join(f"{v} {k}" for k, v in c.items()) + ' |' for room, c in d['counts'].items())
cir = '\n'.join(f"| {c['id']} | {c['name']} | {c['breaker']} | {c['conduit']} |" for c in d['circuits'])
pts = '\n'.join(f"| {p['id']} | {p['roomName']} | {p['label']} | {p['ITM'][0]-179500:.2f}, {p['ITM'][1]-576200:.2f} | {('תקרה ' + format(p['rel'], '+.2f')) if p['onCeiling'] else (format(p['aboveFloor_m'], '.2f') if p['aboveFloor_m'] is not None else format(p['rel'], '+.2f'))} | {p['circuit'] or '—'} |" for p in d['points'])
ck = f"{d['summary']['checks']} בדיקות, {d['summary']['failed']} נכשלו (כל אביזר קיר על פני הקיר; שקע הרחצה לפחות 0.60 מ' מהמקלחת)"
rooms = '\n'.join(f"| {v['name']} | {v['area_m2']:.1f} | {', '.join(v['doors'] or [])} | {', '.join(v['windows'] or []) or '—'} | {v['source'][:90]} |" for v in d['rooms'].values())
doc = f"""# ח4 – נקודות חשמל בקומה א' (הצעה, 13.11.2026)

**מעמד:** הצעה לאישור אביחי. כמויות וגבהים לפי נוהג מקובל, לא לפי תקן או תוכנית ריהוט.
- נתונים: `data/electrical/points-first.json`, נוצר ע"י `python3 tools/electrical/propose_points_first.py` (קלט: `tools/electrical/points-first-inputs.json`).
- במודל: שכבות ← חשמל ← "נקודות חשמל קומה א'".

**ההחלטה (אביחי, 13.11.2026):** {d['decision']}.

![נקודות חשמל קומה א'](screenshots/h4-first-points.png)

## 1. החדרים
המקור הוא תוויות האדריכל ("חדר", "קומה א' H=2.80", "חלל כלוא") ונקודות האינסטלציה.

| חדר | שטח (מ"ר) | דלתות | חלונות | מקור |
|---|---|---|---|---|
{rooms}

שני חדרי הרחצה נמצאים באזור אחד, כי המחיצה ביניהם לא סגורה בנתונים. חילקתי אותו לפי שתי קבוצות הקבועות.

## 2. כמויות לפי חדר

| חדר | נקודות |
|---|---|
{cnt}

**סה"כ:** {d['summary']['points']} נקודות, {d['summary']['circuits']} מעגלי חשמל ו-**{d['summary']['conduitsUp']} צינורות בעלייה** מעל הלוח הראשי. ההערכה הקודמת הייתה 16–20.

## 3. גבהים (זמני – E6)

מרכז האביזר מעל רצפה גמורה ‎+3.85:
- שקע {Hh['socket']}
- מפסק {Hh['switch']}
- שקע רחצה {Hh['bathSocket']}
- תאורת מראה {Hh['mirrorLight']}
- תרמוסטט {Hh['thermostat']}
- תקשורת {Hh['data']}
- מפסק תריס {Hh['shutterSwitch']}

נקודות התקרה נמצאות בהנמכה, ב-{d['levels']['ceilingAbs']:.2f}.

## 4. מעגלים

| מעגל | מה | מא"ז | צינור |
|---|---|---|---|
{cir}

## 5. כל הנקודות

| מזהה | חדר | נקודה | E, N (‎179500 / 576200+) | גובה מעל הרצפה (מ') | מעגל |
|---|---|---|---|---|---|
{pts}

## 6. בדיקות
{ck}.

## 7. פתוח

| # | נושא |
|---|---|
| E6 | טבלת הגבהים |
| E7 | מיקום המיטה והטלוויזיה בכל חדר. השקעים מפוזרים לאורך הקירות הפנויים, ויוזזו לפי הריהוט |
| E24 | צד הידית בכל דלת, לצורך מיקום המפסק |
| E25 | מרפסות קומה א' (צפון ודרום-מערב): תאורה ושקע מוגן מים – לא נכללו, לאשר |
| E26 | תאורת המדרגות – בקומת הקרקע, עם המחליף שבראש המדרגות |
"""
open(os.path.join(ROOT, 'docs/electrical/05-first-floor-points.md'), 'w', encoding='utf-8').write(doc); print('docs/electrical/05-first-floor-points.md')
