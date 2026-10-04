# TennisSim Club

Un'app Flask che simula tutte le funzionalità del piano **Base** e della **Club Membership** (79,99€/anno) di un'app di ranking tennistico amatoriale.
Giocatori, circoli e tornei sono **inventati** e generati all'avvio in modo deterministico (900 giocatori, ~430 tornei, ~7.000 partite simulate punto per punto). Nessun pagamento è reale: la membership si attiva e si disdice nella sessione del browser.

```bash
cd tennistalker
pip install -r requirements.txt
python app.py          # http://127.0.0.1:5001
python -m pytest tests # test del motore e di tutte le pagine
```

Scegli un giocatore come tuo profilo (*Scegli profilo* → *Sono io*), poi attiva la membership da *Club Membership*.

## Funzionalità

| Piano | Funzionalità | Pagina | Come funziona |
|---|---|---|---|
| Base | Classifica simulata in tempo reale | `/classifica` | Partite dell'anno solare, avversari valutati alla categoria ufficiale |
| Base | Esplora i giocatori italiani | `/giocatori`, `/giocatore/<id>` | Elenco per regione/sesso ordinato per classifica simulata |
| Base | Cerca le competizioni | `/competizioni` | Filtri per regione, superficie, limite di categoria, sesso, date; tabelloni e iscritti |
| Club | Classifica Armonizzata | `/classifica/armonizzata` | Ogni avversario vale per la sua categoria *simulata*; proiezione lineare a fine anno |
| Club | Classifica Supersimulata | `/classifica/supersimulata` | Finestra mobile di 12 mesi, passaggi trimestrali, grafico mese per mese |
| Club | Radar Tornei | `/radar` | Score 0–100: punti in palio, probabilità di avanzare (Elo per superficie), superficie, distanza, tempistica |
| Club | Simula Partita | `/simula` | 2.000 simulazioni punto per punto, punteggi probabili, testa a testa, avversari comuni, scouting e piano di gioco |
| Club | Forze & Debolezze | `/analisi` | Grafico radar su 8 assi + forze/debolezze testuali (superfici, tie-break, set decisivi, rimonte…) |
| Club | Posizione assoluta / nazionale / regionale / circolo | `/posizione` | Posizione e vicini di classifica nei quattro ambiti |
| Club | Ricerca avanzata senza restrizioni | `/ricerca` | Base: solo nome, 5 risultati. Club: regione, circolo, sesso, categoria, età, trend, ordinamenti |
| Club | 15% sconto Tennis Warehouse Europe | `/sconto` | Codice coupon fittizio generato per il membro |

## I tuoi dati reali

Nella pagina **I miei dati** (`/i-miei-dati`) puoi incollare il testo della pagina profilo di un'app di ranking
(seleziona tutto con Ctrl+A / Cmd+A, copia e incolla). L'app estrae nome, fascia d'età, classifica, circolo, regione e
le statistiche aggregate (vinte/perse per classifica dell'avversario, per numero di set, per superficie, per tipo di
competizione, stato di forma) e **ricostruisce** partite che rispettano esattamente quei totali. Date, avversari e
punteggi sono ricostruiti, perché il testo non li contiene. Il tuo profilo diventa quello predefinito e tutte le
funzionalità lavorano su di lui.

Puoi incollare anche la pagina riepilogo del profilo (con "Punti FITP", "Classifica Simulata" e
"Supersimulata"): l'app mostrerà un confronto tra quei valori e i propri.

I valori estratti vengono salvati in `data/il_mio_profilo.json`, che è escluso da git: i tuoi dati non finiscono nel
repository. Per usare un altro percorso imposta la variabile d'ambiente `TENNISSIM_PROFILE`.

## Regolamento di classifica (metodo FITP)

- Valore di ogni vittoria in base a quante classifiche separano l'avversario dalla propria: +2 o più → 120, +1 → 90,
  pari → 60, −1 → 30, −2 → 20, −3 → 15, oltre → 0.
- Si contano le migliori N vittorie: N di base dipende dalla classifica (6 per 4.6, 7 per 4.2/4.1, 9 per 3.1, 16 per 2.1)
  più le vittorie supplementari dalla formula V − E − 2I − 3G (E, I, G = sconfitte con pari, una e due o più classifiche
  inferiori). In 4ª categoria: 4–10 → +1, 11–15 → +2, 16–20 → +3, 21+ → +4; in 3ª: 5–12, 13–18, 19–24, 25+.
- Bonus per assenza di sconfitte con pari o inferiori (almeno 5 incontri): +50 in 4ª categoria.
- Soglie maschili di promozione/retrocessione: 4.NC 80, 4.6 110/60, 4.5 210/90, 4.4 300/120, 4.3 380/190, 4.1 505/255,
  3.5 580. Se si supera la soglia si sale e si **ricalcola sulla nuova classifica** (anche più volte).
- Valori stimati (non trovati nel metodo ufficiale): soglie di 4.2 e dalla 3.4 in su, retrocessione 3.5, alcune
  vittorie di base, tabella supplementari e bonus di 2ª/3ª categoria. Sono in `engine/ranking.py`.
- Per il profilo reale l'armonizzazione non ricalcola gli avversari: quelli ricostruiti non sono le persone reali.

## Struttura

```
engine/
  categories.py  categorie e indici
  simulation.py  simulazione punto per punto (game, tie-break, match tie-break) e Monte Carlo
  data.py        generazione del mondo sintetico (giocatori, circoli, tornei, tabelloni)
  ranking.py     coefficiente, armonizzata, supersimulata, posizioni
  analysis.py    Elo, Forze & Debolezze, Simula Partita, Radar Tornei
  personal.py    lettura del profilo reale incollato e ricostruzione delle partite
  charts.py      coordinate dei grafici SVG
app.py           route Flask e controllo accessi Base/Club
templates/, static/style.css
tests/test_app.py
```
