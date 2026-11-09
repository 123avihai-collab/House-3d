# ממצאי הבדיקות – הצעת האינסטלציה (routes.json, לפני עריכה)

נוצר ע"י `node tools/plumbing/editor_findings.mjs` – אותן בדיקות שרצות בעורך. סה"כ 34 ממצאים.

| סוג | unit | ground | site | first | roof | סה"כ |
|---|---|---|---|---|---|---|
| ⛔ חוצה עמוד |  | 1 |  |  |  | 1 |
| ⛔ חוצה קורה | 1 | 12 |  | 3 |  | 16 |
| ⛔ בתוך בטון | 2 | 2 |  |  |  | 4 |
| ⛔ עובר בחצר האנגלית | 4 | 4 |  | 1 |  | 9 |
| ⚠ מעבר בקיר לא בניצב | 2 |  |  |  |  | 2 |
| ⚠ שיפוע נמוך |  |  |  | 2 |  | 2 |

## שגיאות (⛔) – כל הרשימה

| קומה | קו | מערכת | ממצא | אלמנט (מקור) |
|---|---|---|---|---|
| unit | C-UNIT1-basin | cold | קטע אנכי בתוך קיר מרתף BW1 | קיר מרתף BW1 (data/structure/framing.json basementWalls) |
| unit | C-UNIT1-shower | cold | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| unit | H-UNIT1-basin | hot | קטע אנכי בתוך קיר מרתף BW1 | קיר מרתף BW1 (data/structure/framing.json basementWalls) |
| unit | H-UNIT1-shower | hot | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| unit | PB6-UNIT1-shower | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| unit | PB6-VENT | vent | חוצה קורה B-8 (+6.65…+8.00) במפלס +6.63 | קורה B-8 (data/structure/floor-roof.json ceiling.beams) |
| unit | PSTACK3-C5 | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| ground | C-BS4@ground | cold | קטע אנכי בתוך קיר בטון GW3 | קיר בטון GW3 (data/structure/floor-ground.json) |
| ground | C-WC2@ground | cold | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | H-BS4@ground | hot | קטע אנכי בתוך קיר בטון GW3 | קיר בטון GW3 (data/structure/floor-ground.json) |
| ground | MAIN-ENTRY | cold | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| ground | PR1-1-DPS1@ground | rain | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.12 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS1@ground | rain | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.48 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS1@ground | rain | חוצה קורה B-37 (−0.75…−0.15) במפלס −0.56 | קורת יסוד B-37 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS1@ground | rain | חוצה קורה B-39 (−0.75…−0.15) במפלס −0.61 | קורת יסוד B-39 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS1@ground | rain | חוצה קורה B-38 (−0.75…−0.15) במפלס −0.63 | קורת יסוד B-38 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS2@ground | rain | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.12 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS2@ground | rain | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.63 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS3@ground | rain | חוצה קורה B-39 (−0.75…−0.15) במפלס −0.10 | קורת יסוד B-39 (data/structure/framing.json groundBeams) |
| ground | PR1-1-DPS3@ground | rain | חוצה קורה B-39 (−0.75…−0.15) במפלס −0.49 | קורת יסוד B-39 (data/structure/framing.json groundBeams) |
| ground | PSTACK2 | sewage | חוצה עמוד C1 במפלס +6.40 | עמוד C1 (data/structure/floor-first.json) |
| ground | PSTACK3 | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| ground | PSTACK3-C1 | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| ground | PSTACK3-C2 | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |
| ground | PSTACK6-C1 | sewage | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.86 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PSTACK6-C2 | sewage | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.86 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| first | PL3-SW1@first | sewage | חוצה קורה קורה ללא מספר 30/60 (+3.05…+3.65) במפלס +3.69 | קורה קורה ללא מספר 30/60 (data/structure/floor-ground.json ceiling.beams) |
| first | PL3-SW1@first | sewage | חוצה קורה קורה ללא מספר 30/60 (+3.05…+3.65) במפלס +3.38 | קורה קורה ללא מספר 30/60 (data/structure/floor-ground.json ceiling.beams) |
| first | PSTACK3-C4 | sewage | חוצה קורה B-13 (+3.45…+4.15) במפלס +3.75 | קורה B-13 (data/structure/floor-ground.json ceiling.beams) |
| first | PSTACK3-C4 | sewage | עובר בחצר האנגלית (אסור – גם מתחת לבטון) | חצר אנגלית (רשת מדרך) חצר (data/structure/floor-ground.json openZones (courtyard)) |

## אזהרות (⚠)

| קומה | קו / נקודה | ממצא |
|---|---|---|
| unit | PB6-RISING | חוצה קיר מרתף BW1 בזווית 54.5° (לא בניצב) |
| unit | PB6-RISING | חוצה קיר מרתף BW1 בזווית 70.1° (לא בניצב) |
| first | PL3-SW1@first | שיפוע 0.83% – מתחת ל-2.0% |
| first | PL3-SW2@first | שיפוע 1.85% – מתחת ל-2.0% |
