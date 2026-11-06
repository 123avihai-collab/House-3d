# sources/ — קבצי המקור

כל מידה, מיקום וגובה במודל נגזרים רק מהקבצים כאן (ראו CLAUDE.md §1).

> **פרטיות:** המאגר ב-GitHub **ציבורי**. קבצי המקור (גרמושקה, מדידה, תוכניות עם שמות בעלים) **לא נשמרים ב-git**. ראו `.gitignore`. כדי לשחזר את התיקייה מורידים את הקבצים מהדרייב לפי המזהים בטבלה, לאותם נתיבים. ההחלטה אם להעלות אותם למאגר (או להפוך אותו לפרטי) ממתינה לאישור אביחי (docs/open-issues.md).

## קבצים בשימוש בשלב 1

| נתיב מקומי | שם מקורי בדרייב | Drive file id | שימוש |
|---|---|---|---|
| `survey/survey-5187-tzachi-abitan.pdf` | רקפות - 5187 מדידת שטח - צחי אביטן.pdf | `14rrrecPVkXtXwgi7lFHdZqdy36P05fxk` | **המדידה** (סרוקה, 25.09.2025): טבלת נקודות גבול, שטח רשום 498, מידות צלעות, גבהים קיימים |
| `survey/INDEX_F02628-36-MIG-5187.dwg` | INDEX_F02628-36-MIG-5187.dwg | `1qXsC5CD897pXKN_P3JKf0B5afKCO0aO9` | **מפה למשתכן** (חץ הצפון, 08-05-2023), DWG ב-ITM: נקודות גבול, גבהים מתוכננים (מגרש, מדרכה, ±0.00), קווי גובה מתוכננים, אבני שפה, קווי בניין, גבולות חלקות (תרשים 1:5000) |
| `survey/INDEX_F02628-25-SHIVUK-MIG-5187.pdf` | INDEX_F02628-25-SHIVUK-MIG-5187.pdf | `11dnEyAuC9qyyNMLS737un5b81tC9tRLM` | מפת שיווק: אימות קואורדינטות ושטח 0.498 דונם |
| `permit/permit-sheet1-gramushka.dwg` | "…-Sheet - 1 - גרמושקא.dwg" (שם הקובץ כולל את שמות הבעלים) | `1iZBRT1fwHWkWjT2SlMlV9HuHJwDD9hgX` | גרמושקה (עדכני מה-DXF, 29.09 לעומת 31.08): אימות ±0.00 = 280.50, גבהי "לפי המשתכן" |
| `zoning/tamal-1016-instructions.pdf` | 1016 הוראות התכנית מס תמל.pdf | `1oy_q5_A2GP9UZuCdsUyy0uzWwnCLTQmU` | תמל/1016 §4.1.2 (סרוק, OCR): טיפוס A – 2 קומות, קווי בניין 3/3/5 |
| `zoning/tamal-1016-proposed-state-residential-A.pdf` | מצב מוצע מתכנית מאושרת מס' תמל 1016 - מגורים א' .צמודי קרקע.pdf | `1CW1G0GQHzJss6hHtl03F7LhOl1P5NiJ-` | טבלה 5 – זכויות והוראות בנייה |
| `zoning/plan-605-0843136-amending-tamal-1016-instructions.pdf` | הוראות תוכנית שמשנה את תמל 1016 605-0843136.pdf | `1ReZdfboYmLZeRZo66SlG_2_fHzrTZtgX` | נבדק – לא חל על מגרש 5187 |
| `neighborhood/types-diagram-north-with-requests.pdf` | תרשים טיפוסים - חלק צפוני עם מספרי בקשה.pdf | `1YmzBHLBc-oIrcpB10QUxWgwDHhvrSH58` | מקרא טיפוסים (A1/A2…) |
| `neighborhood/type-A1-elevations-sections-ed108.pdf` | תכנית חזיתות וחתכים טיפוס A1 מהדורה 108.pdf | `1mV_AQiWaw6psQ_dG8eGz9MSlvbK5kew4` | נבדק – אין גובה מבנה מקסימלי במטרים |
| `neighborhood/analytic-map-rakafot.pdf` | מפה אנליטית שכונת רקפות … .pdf | `1AzhGDTFu8Fvqiy_ih4gFO7RVR3z5BIz6` | נבדק – הקואורדינטות ב-PDF מעוגלות ל-0.83 מ', לא שמיש לגיאומטריה |

## קבצים שלא ניתן היה להוריד (מעל 10MB – מגבלת הכלי)

| שם | גודל | השפעה |
|---|---|---|
| "…-Sheet - 1 - גרמושקא.dxf" | 36MB | הוחלף ב-DWG של אותו גיליון (גרסה מאוחרת יותר) |
| תכנית בינוי גיליון 01–05 מתחם B1.pdf | 11–14MB | גבהי פיתוח מעבר למסגרת המפה למשתכן – ראו docs/open-issues.md |
| חתום נספח צמחיה-פיתוח-פרטים-רחובות טיפוסיים.pdf | 23MB | חתכי רחוב טיפוסיים (רוחב מדרכה, אבן שפה) |

## גאורפרנס

| מקור | שיטה | שארית |
|---|---|---|
| מפה למשתכן – מפה ראשית | ITM מקורי ב-DWG | 0.004 מ' מול טבלת המדידה (עיגול) |
| מפה למשתכן – תרשים 1:5000 | התאמת דמיון ל-8 נקודות גבול | ‏9e-11 מ' (העתק מוקטן מדויק ×5) |
| גרמושקה – בלוק "מפת מדידה" | התאמת דמיון ל-5 נקודות | 0.008 מ' |
| מדידה סרוקה 2025 | אפינית ל-5 נקודות גבול (300dpi, סיבוב לצפון) | 0.06–0.14 מ' – גבהים קיימים בלבד |

## צינור החילוץ

```
node tools/dwg2json/convert.mjs sources/survey/INDEX_F02628-36-MIG-5187.dwg tools/cache/mig-5187.json
node tools/dwg2json/convert.mjs sources/permit/permit-sheet1-gramushka.dwg tools/cache/permit-sheet1.json
python3 tools/extract_site.py      # -> data/site/*.json
python3 tools/derive_site.py       # -> terrain-regions.json, neighbors.json
node tools/verify_stage1.mjs       # -> docs/verification/stage-1.md
```
קריאות ידניות (מתועדות, עם מקור): `tools/contour-levels.json`, `tools/survey-2025-points.json`, `tools/survey-2025-georef.json`, `tools/verification-sources.json`.
