# ניקוי המאגר – 13.11.2026

בקשת אביחי: לסרוק את המודל, למצוא מה לא נחוץ ולהקטין. **שום דבר שהמודל מציג ושום ערך מדוד לא השתנו**; `sources/` לא נגע.

כל פריט נבדק לפני הסרה: חיפוש בכל המאגר (md / json / py / js / mjs / html / css), וגרף ה-import המלא משלושת הדפים (`index.html`, `editor.html`, `plans.html`), מ-`tests/` ומ-`tools/*.mjs`.

## מה הוסר / הוקטן

| # | מה | לפני | אחרי | חיסכון | הסיבה |
|---|---|---|---|---|---|
| 1 | `assets/textures/*/{color,roughness,ao}.jpg` – 44 קובצי JPG של 15 ערכות טקסטורה | 26.30 MB | 0 | **26.30 MB** | הצופה טוען רק `color/roughness/ao.webp` ו-`normal.jpg` (`js/core/materials.js`, `src/tiling/workshop.js`, `src/tiling/pool.js`). ה-JPG היו רק חומר המקור של `tools/optimize_textures.py`, ואף קובץ לא טוען אותם; הם גם פורסמו לחינם לארטיפקט. לכל אחד קיים WebP תואם. אפשר להוריד שוב מ-Poly Haven (`assets/CREDITS.json`). |
| 2 | `vendor/three/examples/jsm/` – 112 תוספות three.js שלא מיובאות | 0.81 MB | 0 | **0.81 MB** | לא נגישות מאף דף (גם לא בעקיפין). נשארו 21 הקבצים שבשימוש (OrbitControls, Line2 ותלויותיו, HDRLoader, EffectComposer / RenderPass / GTAOPass / OutputPass ותלויותיהם, CSS2DRenderer, BufferGeometryUtils, SimplexNoise), `build/` וקובצי ה-LICENSE. |
| 3 | `docs/**/*.png` – 85 צילומי מסך, דחיסה מחדש **ללא אובדן** (oxipng, רמה 5) | 77.62 MB | 70.50 MB | **7.12 MB** | אותם שמות ואותו פורמט; כל קובץ אומת פיקסל-לפיקסל מול המקור לפני ההחלפה. |
| | **סה"כ** | 279.60 MB | 245.36 MB | **34.24 MB** | (עץ העבודה, בלי `.git`) |

קבצים שפורסמו לארטיפקט (`tools/build_artifact.py`): ירדו ב-156 (44 JPG + 112 קובצי vendor), כ-27 MB פחות בכל פרסום.

שינוי קוד יחיד: `tools/optimize_textures.py` מוחק עכשיו את ה-JPG אחרי ההמרה ל-WebP (כדי שערכה חדשה לא תחזיר את הכפילות).

## מה נבדק ונמצא תקין (לא נדרש שינוי)

- **טקסטורות:** כל 16 הערכות + `at12625/faces.webp` מופנות מ-`data/` (חומרים / קטלוג ריצוף). כולן כבר 1024×1024 – אין מה להקטין. ה-HDRI (2k, ‏4.6 MB) בשימוש.
- **`data/`:** כל הקבצים רשומים ב-`data/manifest.json` או נקראים מ-js / src / tools / tests, חוץ מתיקיית הגיבוי שבסעיף 2 למטה.
- **קוד:** כל המודולים ב-`js/` ו-`src/` נגישים מאחד הדפים; אין `console.log` / `debugger`; אין לשוניות שמפנות לתכונות שהוסרו.
- **קבצים זמניים:** אין `*.bak`, `*.zip`, `*tmp*`, `__pycache__` או `node_modules` במאגר.
- **`vendor/xlsx`, `vendor/delaunator`:** בשימוש (יצוא Excel; טריאנגולציית הקרקע).

## מועמדים שלא הוסרו – דורשים החלטה של אביחי

1. **צילומי מסך ב-`docs/` שאף מסמך md לא מפנה אליהם – 84 קבצים, ‎62.6 MB** (אחרי הדחיסה). אלה תיעוד של שלבים שכבר אושרו; מחיקה שלהם היא החיסכון הגדול ביותר שנותר, אבל זו החלטה על תיעוד ולא על "זבל" ודאי:
   - `docs/screenshots/` – 23 קבצים, 24.5 MB (שלבים 1 / 2 / 2ב, סביבה, OC-1, פאנלים)
   - `docs/plumbing/screenshots/` – 34 קובצי JPG, 15.9 MB (הצעה, עורך, ניתוב מחדש)
   - `docs/finishes/screenshots/` – 17 קבצים, 13.5 MB (מתוכם `round4/` – 10 קבצים; `plaster-round4.md` מפנה לתיקייה, לא לקבצים)
   - `docs/verification/` – 9 קבצים, 7.7 MB (`stage-2b-pool*.png`, `stage-3-*.png`, `sheet-overlay-K-*.png`, `section-preset-h40.png`)
   - `docs/electrical/screenshots/h1-step2-conduits.png` – 1.0 MB
2. **`data/plumbing/edits-backup-2026-11-09/`** (27 קבצים, 116 KB) – גיבוי 27 העריכות הידניות של אביחי בעורך (ED22 ב-`open-issues.md`, מסומן ✅). שום קוד לא קורא אותו, אבל הוא מפורסם לארטיפקט עם `data/`. הצעה: להעביר ל-`docs/plumbing/` או למחוק.
3. **התיקייה `העתק למודל - חזיתות + חתכים/`** (6 קובצי PDF, 1.2 MB) – **חומר מקור חי, לא זבל.** `tools/extract_mamad.py` קורא ממנה, שדות `source` ב-`data/architecture/mamad.json` ו-`openings.json` מפנים אליה, והיא מתועדת ב-`sources/README.md`. קובץ אחד (`חתך א-א - חזית מערב - מטבח+קומה א' מזדרון…pdf`) זהה בית-לבית לעותק ב-`sources/architecture/`. המלצה: להעביר את 5 הקבצים האחרים ל-`sources/architecture/`, למחוק את הכפול ולעדכן את ההפניות (כלי אחד, שני קובצי נתונים, שני מסמכים). לא בוצע – שינוי במקורות דורש אישור.
4. **`buildOpenings` ב-`js/geometry/openings.js`** – הפונקציה לא נקראת (חלונות ודלתות "בהמתנה", החלטת אביחי 07.11). נשארה במקומה כי היא מיועדת לשלב עתידי.
5. **צילומי ה-JPG ב-`docs/`** (41 קבצים, 17.7 MB) – לא נדחסו מחדש: אין במכונה כלי לדחיסת JPEG ללא אובדן, ושמירה מחדש הייתה פוגעת באיכות.
6. **`data/finishes/plaster/surfaces.json`** (2.1 MB) – הקובץ הגדול ב-`data/`. בשימוש; אפשר לכתוב אותו בלי רווחים והזחות, אבל זה שינוי בצינור (`tools/finishes/`) ולא ניקוי.
7. **היסטוריית git** – הקבצים שהוסרו עדיין קיימים בהיסטוריה. הקטנת ה-`.git` עצמו מחייבת שכתוב היסטוריה (force-push) – לא בוצע.

## אימות

- `npm test` עבר (בדיקת נתונים + כל בדיקות הדפדפן, בלי שגיאות קונסול ובלי 404 על טקסטורה או מודול).
- `python3 tools/build_artifact.py` – 283 קבצים לפרסום.

## סבב 2 – החלטות אביחי (14.11.2026)

| # | פעולה | חיסכון |
|---|---|---|
| 1 | נמחקו 82 צילומי מסך ב-`docs/` שאף קובץ לא מפנה אליהם (docs/screenshots, docs/plumbing/screenshots, docs/finishes/screenshots כולל round4, 8 ב-docs/verification). לא נדרשים להמשך הבנייה – אפשר להפיק מחדש מהמודל | 60.6 MB |
| 2 | נמחק הגיבוי `data/plumbing/edits-backup-2026-11-09/` (27 קבצים) | 0.1 MB |
| 3 | "העתק למודל - חזיתות + חתכים" הועברה ל-`sources/architecture/` (5 קבצים); העותק הכפול של "חתך א-א – חזית מערב" הוסר. עודכנו `tools/extract_mamad.py`, `data/architecture/mamad.json`, `openings.json`, `docs/verification/mamad.md`, `sources/README.md`. החילוץ הורץ מחדש – רק שדות `source` השתנו | 0.2 MB |
| 4 | היסטוריית Git – לא משוכתבת (החלטה) | – |
