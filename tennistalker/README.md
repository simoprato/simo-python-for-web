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

I valori estratti vengono salvati in `data/il_mio_profilo.json`, che è escluso da git: i tuoi dati non finiscono nel
repository. Per usare un altro percorso imposta la variabile d'ambiente `TENNISSIM_PROFILE`.

## Regolamento di classifica (semplificato, ispirato a quello FITP)

- Categorie dalla 4.NC alla 2.1.
- Valore vittoria in base alla differenza di categoria con l'avversario: +2 o più → 120, +1 → 90, pari → 60, −1 → 40, −2 → 30, −3 → 20, oltre → 10.
- Si sommano le migliori **K** vittorie, con K = 6 + (vittorie − sconfitte) / 2 (tra 4 e 14), più i bonus (torneo vinto +25, finale +10, nessuna sconfitta con categorie inferiori +20).
- Promozione se il coefficiente ≥ `300 + 20 × indice categoria` (doppia oltre 1,8×); retrocessione sotto il 40% della soglia con almeno 4 partite.

Non è il regolamento ufficiale: i valori sono stati scelti per produrre una distribuzione plausibile di promozioni e retrocessioni.

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
