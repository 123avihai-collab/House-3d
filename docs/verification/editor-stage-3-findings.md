# ממצאי הבדיקות – הצעת האינסטלציה (routes.json, לפני עריכה)

נוצר ע"י `node tools/plumbing/editor_findings.mjs` – אותן בדיקות שרצות בעורך. סה"כ 122 ממצאים.

| סוג | unit | ground | site | first | roof | סה"כ |
|---|---|---|---|---|---|---|
| ⛔ חוצה עמוד |  | 2 |  |  |  | 2 |
| ⛔ חוצה קורה | 1 | 19 |  | 4 |  | 24 |
| ⛔ בתוך בטון |  | 2 |  | 1 |  | 3 |
| ⚠ מעבר בקיר לא בניצב | 2 | 53 |  | 36 |  | 91 |
| ⚠ שיפוע נמוך |  |  |  | 2 |  | 2 |

## שגיאות (⛔) – כל הרשימה

| קומה | קו | מערכת | ממצא | אלמנט (מקור) |
|---|---|---|---|---|
| unit | PB6-VENT | vent | חוצה קורה B-8 (+6.65…+8.00) במפלס +6.63 | קורה B-8 (data/structure/floor-roof.json ceiling.beams) |
| ground | C-BS3@ground | cold | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | C-BS4@ground | cold | קטע אנכי בתוך קיר בטון GW3 | קיר בטון GW3 (data/structure/floor-ground.json) |
| ground | C-SH2@ground | cold | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | C-WC2@ground | cold | חוצה עמוד C8 במפלס −0.07 | עמוד C8 (data/structure/floor-ground.json) |
| ground | C-WC2@ground | cold | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | FEED-GROUND | cold | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | H-BS3@ground | hot | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | H-BS4@ground | hot | קטע אנכי בתוך קיר בטון GW3 | קיר בטון GW3 (data/structure/floor-ground.json) |
| ground | H-SH2@ground | hot | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| ground | HOT-GROUND | hot | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
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
| ground | PSTACK6-C1 | sewage | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.86 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | PSTACK6-C2 | sewage | חוצה קורה B-53 (−1.07…−0.17) במפלס −0.86 | קורת יסוד B-53 (data/structure/framing.json groundBeams) |
| ground | RET-GROUND | return | חוצה קורה B-44 (−0.40…+0.20) במפלס −0.07 | קורת יסוד B-44 (data/structure/framing.json groundBeams) |
| first | C-BT2@first | cold | חוצה קורה B-28 (+3.45…+4.05) במפלס +3.78 | קורה B-28 (data/structure/floor-ground.json ceiling.beams) |
| first | C-WC1@first | cold | קטע אנכי בתוך קיר בטון FW6 | קיר בטון FW6 (data/structure/floor-first.json) |
| first | PL3-SW1@first | sewage | חוצה קורה קורה ללא מספר 30/60 (+3.05…+3.65) במפלס +3.69 | קורה קורה ללא מספר 30/60 (data/structure/floor-ground.json ceiling.beams) |
| first | PL3-SW1@first | sewage | חוצה קורה קורה ללא מספר 30/60 (+3.05…+3.65) במפלס +3.38 | קורה קורה ללא מספר 30/60 (data/structure/floor-ground.json ceiling.beams) |
| first | PSTACK3-C4 | sewage | חוצה קורה B-13 (+3.45…+4.15) במפלס +3.75 | קורה B-13 (data/structure/floor-ground.json ceiling.beams) |

## אזהרות (⚠)

| קומה | קו / נקודה | ממצא |
|---|---|---|
| unit | PB6-RISING | חוצה קיר מרתף BW1 בזווית 54.5° (לא בניצב) |
| unit | PB6-RISING | חוצה קיר מרתף BW1 בזווית 70.1° (לא בניצב) |
| ground | C-WC2@ground | חוצה קיר בלוקים BK-G22 בזווית 72.4° (לא בניצב) |
| ground | C-BS3@ground | חוצה קיר בלוקים BK-G22 בזווית 73.2° (לא בניצב) |
| ground | H-BS3@ground | חוצה קיר בלוקים BK-G22 בזווית 71.7° (לא בניצב) |
| ground | H-BS3@ground | חוצה קיר בלוקים BK-G22 בזווית 67.8° (לא בניצב) |
| ground | C-SH2@ground | חוצה קיר בלוקים BK-G22 בזווית 69.0° (לא בניצב) |
| ground | C-SH2@ground | חוצה קיר בלוקים BK-G41 בזווית 70.0° (לא בניצב) |
| ground | H-SH2@ground | חוצה קיר בלוקים BK-G22 בזווית 69.3° (לא בניצב) |
| ground | C-SK1@ground | חוצה קיר בלוקים BK-G14 בזווית 73.7° (לא בניצב) |
| ground | C-SK1@ground | חוצה קיר בלוקים BK-G14 בזווית 71.6° (לא בניצב) |
| ground | H-SK1@ground | חוצה קיר בלוקים BK-G14 בזווית 72.8° (לא בניצב) |
| ground | H-SK1@ground | חוצה קיר בלוקים BK-G14 בזווית 72.3° (לא בניצב) |
| ground | H-SK1@ground | חוצה קיר בלוקים BK-G50 בזווית 29.9° (לא בניצב) |
| ground | C-BS4@ground | חוצה קיר בלוקים BK-G14 בזווית 75.9° (לא בניצב) |
| ground | C-BS4@ground | חוצה קיר בלוקים BK-G14 בזווית 81.5° (לא בניצב) |
| ground | C-BS4@ground | חוצה קיר בלוקים BK-G2 בזווית 67.9° (לא בניצב) |
| ground | C-BS4@ground | חוצה קיר בטון GW3 בזווית 53.5° (לא בניצב) |
| ground | H-BS4@ground | חוצה קיר בלוקים BK-G14 בזווית 75.9° (לא בניצב) |
| ground | H-BS4@ground | חוצה קיר בלוקים BK-G14 בזווית 81.5° (לא בניצב) |
| ground | H-BS4@ground | חוצה קיר בלוקים BK-G2 בזווית 67.3° (לא בניצב) |
| ground | H-BS4@ground | חוצה קיר בטון GW3 בזווית 83.0° (לא בניצב) |
| ground | C-SH1@ground | חוצה קיר בלוקים BK-G14 בזווית 31.1° (לא בניצב) |
| ground | C-SH1@ground | חוצה קיר בלוקים BK-G14 בזווית 20.7° (לא בניצב) |
| ground | C-SH1@ground | חוצה קיר בלוקים BK-G16 בזווית 49.3° (לא בניצב) |
| ground | C-SH1@ground | חוצה קיר בלוקים BK-G16 בזווית 80.5° (לא בניצב) |
| ground | H-SH1@ground | חוצה קיר בלוקים BK-G14 בזווית 26.9° (לא בניצב) |
| ground | H-SH1@ground | חוצה קיר בלוקים BK-G14 בזווית 50.3° (לא בניצב) |
| ground | H-SH1@ground | חוצה קיר בלוקים BK-G16 בזווית 65.7° (לא בניצב) |
| ground | C-WC1@ground | חוצה קיר בלוקים BK-G14 בזווית 18.7° (לא בניצב) |
| ground | C-WC1@ground | חוצה קיר בלוקים BK-G15 בזווית 47.2° (לא בניצב) |
| ground | C-WC1@ground | חוצה קיר בלוקים BK-G16 בזווית 75.5° (לא בניצב) |
| ground | C-WC1@ground | חוצה קיר בלוקים BK-G16 בזווית 68.5° (לא בניצב) |
| ground | C-WC1@ground | חוצה קיר בלוקים BK-G10 בזווית 50.2° (לא בניצב) |
| ground | C-WC3@ground | חוצה קיר בלוקים BK-G14 בזווית 43.1° (לא בניצב) |
| ground | C-WC3@ground | חוצה קיר בלוקים BK-G14 בזווית 60.9° (לא בניצב) |
| ground | C-WC3@ground | חוצה קיר בלוקים BK-G2 בזווית 68.6° (לא בניצב) |
| ground | C-BS1@ground | חוצה קיר בלוקים BK-G14 בזווית 59.3° (לא בניצב) |
| ground | C-BS1@ground | חוצה קיר בלוקים BK-G14 בזווית 77.0° (לא בניצב) |
| ground | C-BS1@ground | חוצה קיר בלוקים BK-G16 בזווית 73.2° (לא בניצב) |
| ground | C-BS1@ground | חוצה קיר בלוקים BK-G16 בזווית 62.4° (לא בניצב) |
| ground | H-BS1@ground | חוצה קיר בלוקים BK-G14 בזווית 46.1° (לא בניצב) |
| ground | H-BS1@ground | חוצה קיר בלוקים BK-G14 בזווית 83.2° (לא בניצב) |
| ground | H-BS1@ground | חוצה קיר בלוקים BK-G16 בזווית 76.1° (לא בניצב) |
| ground | H-BS1@ground | חוצה קיר בלוקים BK-G16 בזווית 61.0° (לא בניצב) |
| ground | C-BS2@ground | חוצה קיר בלוקים BK-G14 בזווית 62.3° (לא בניצב) |
| ground | C-BS2@ground | חוצה קיר בלוקים BK-G14 בזווית 53.2° (לא בניצב) |
| ground | C-BS2@ground | חוצה קיר בלוקים BK-G16 בזווית 85.6° (לא בניצב) |
| ground | C-BS2@ground | חוצה קיר בלוקים BK-G16 בזווית 68.9° (לא בניצב) |
| ground | H-BS2@ground | חוצה קיר בלוקים BK-G14 בזווית 83.5° (לא בניצב) |
| ground | H-BS2@ground | חוצה קיר בלוקים BK-G16 בזווית 74.7° (לא בניצב) |
| ground | FEED-GROUND | חוצה קיר בלוקים BK-G22 בזווית 67.9° (לא בניצב) |
| ground | HOT-GROUND | חוצה קיר בלוקים BK-G22 בזווית 79.3° (לא בניצב) |
| ground | RET-GROUND | חוצה קיר בלוקים BK-G22 בזווית 86.7° (לא בניצב) |
| ground | PSTACK1 | חוצה קיר בלוקים BK-F72 בזווית 73.3° (לא בניצב) |
| first | C-WC1@first | חוצה קיר בלוקים BK-F53 בזווית 67.2° (לא בניצב) |
| first | C-WC1@first | חוצה קיר בלוקים BK-F53 בזווית 68.5° (לא בניצב) |
| first | C-WC1@first | חוצה קיר בלוקים BK-F54 בזווית 62.4° (לא בניצב) |
| first | C-WC1@first | חוצה קיר בטון FW6 בזווית 39.1° (לא בניצב) |
| first | C-WC2@first | חוצה קיר בלוקים BK-F53 בזווית 82.2° (לא בניצב) |
| first | C-WC2@first | חוצה קיר בלוקים BK-F53 בזווית 15.2° (לא בניצב) |
| first | C-WC2@first | חוצה קיר בלוקים BK-F53 בזווית 51.7° (לא בניצב) |
| first | C-WC2@first | חוצה קיר בלוקים BK-F53 בזווית 56.6° (לא בניצב) |
| first | C-SH2@first | חוצה קיר בלוקים BK-F53 בזווית 67.2° (לא בניצב) |
| first | C-SH2@first | חוצה קיר בלוקים BK-F53 בזווית 68.7° (לא בניצב) |
| first | C-SH2@first | חוצה קיר בלוקים BK-F54 בזווית 77.7° (לא בניצב) |
| first | C-SH2@first | חוצה קיר בטון FW6 בזווית 86.3° (לא בניצב) |
| first | H-SH2@first | חוצה קיר בלוקים BK-F53 בזווית 61.6° (לא בניצב) |
| first | H-SH2@first | חוצה קיר בלוקים BK-F53 בזווית 69.0° (לא בניצב) |
| first | H-SH2@first | חוצה קיר בלוקים BK-F54 בזווית 65.0° (לא בניצב) |
| first | C-SH1@first | חוצה קיר בלוקים BK-F53 בזווית 65.3° (לא בניצב) |
| first | H-SH1@first | חוצה קיר בלוקים BK-F53 בזווית 68.0° (לא בניצב) |
| first | H-SH1@first | חוצה קיר בלוקים BK-F53 בזווית 73.4° (לא בניצב) |
| first | C-BS2@first | חוצה קיר בלוקים BK-F53 בזווית 60.6° (לא בניצב) |
| first | C-BS2@first | חוצה קיר בלוקים BK-F53 בזווית 81.4° (לא בניצב) |
| first | C-BS2@first | חוצה קיר בלוקים BK-F54 בזווית 42.3° (לא בניצב) |
| first | C-BS2@first | חוצה קיר בטון FW6 בזווית 55.5° (לא בניצב) |
| first | H-BS2@first | חוצה קיר בלוקים BK-F53 בזווית 78.0° (לא בניצב) |
| first | H-BS2@first | חוצה קיר בלוקים BK-F53 בזווית 76.2° (לא בניצב) |
| first | H-BS2@first | חוצה קיר בלוקים BK-F54 בזווית 18.0° (לא בניצב) |
| first | H-BS2@first | חוצה קיר בטון FW6 בזווית 71.8° (לא בניצב) |
| first | C-BS1@first | חוצה קיר בלוקים BK-F53 בזווית 87.6° (לא בניצב) |
| first | C-BS1@first | חוצה קיר בלוקים BK-F53 בזווית 36.0° (לא בניצב) |
| first | H-BS1@first | חוצה קיר בלוקים BK-F53 בזווית 77.5° (לא בניצב) |
| first | H-BS1@first | חוצה קיר בלוקים BK-F53 בזווית 71.7° (לא בניצב) |
| first | C-BT1@first | חוצה קיר בלוקים BK-F59 בזווית 47.7° (לא בניצב) |
| first | C-BT1@first | חוצה קיר בלוקים BK-F61 בזווית 47.7° (לא בניצב) |
| first | C-BT2@first | חוצה קיר בלוקים BK-F58 בזווית 40.3° (לא בניצב) |
| first | C-BT2@first | חוצה קיר בלוקים BK-F59 בזווית 40.3° (לא בניצב) |
| first | PL3-SW1@first | חוצה קיר בלוקים BK-G47 בזווית 17.0° (לא בניצב) |
| first | PL3-SW1@first | שיפוע 0.83% – מתחת ל-2.0% |
| first | PL3-SW2@first | חוצה קיר בלוקים BK-G9 בזווית 87.8° (לא בניצב) |
| first | PL3-SW2@first | שיפוע 1.85% – מתחת ל-2.0% |
