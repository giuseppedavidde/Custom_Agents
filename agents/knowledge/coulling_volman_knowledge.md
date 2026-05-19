# KNOWLEDGE BASE: STRATEGIA QUANTITATIVA MULTI-ASSET (VPA & PRICE ACTION)

## Metriche e Parametri Operativi Base
* Timeframe di riferimento: **5** minuti.
* Media Mobile di riferimento: **25** EMA (Exponential Moving Average).
* Obiettivo di profitto standard (Target): **20** pip/tick.
* Stop Loss standard: **10** pip/tick.
* Magneti di Prezzo: Livelli tondi psicologici (**00**, **50**) o livelli decennali (**20**, **40**, **60**, **80**),,.

## Gestione del Rischio e Regole Generali

> **Regola d'Oro 1**: Non anticipare mai l'evento. L'ingresso scatta esclusivamente quando la candela di segnale viene superata di esattamente **1** pip.
> **Regola d'Oro 2**: Valutare sempre la presenza di ostacoli. Evitare i trade in cui i livelli magnete avversi (**00** o **50**) si trovano sul percorso dello Stop Loss o impediscono fisicamente il raggiungimento del target di **20** pip,.
> **Regola d'Oro 3**: L'analisi dei volumi è multi-livello. Valutare il micro (candela singola), il macro (ultime candele vicine) e il globale (trend generale, supporti e resistenze),.

---

## Analisi Anomalie Prezzo-Volume (Anna Coulling)

### Anomalia 1: Sforzo senza Risultato (Narrow Spread / High Volume)
1) **Descrizione visuale della candela**: Spread di prezzo (range tra massimo e minimo) modesto o stretto, corpo contenuto.
2) **Comportamento del volume**: Volume alto o anormalmente alto.
3) **Significato (Accumulazione/Distribuzione)**: Distribuzione. Il mercato avrebbe dovuto muoversi molto di più dato lo sforzo. Segnala potenziale debolezza: i market maker stanno vendendo a questo livello.
4) **Azione da intraprendere**: Identificare il primo segno di manovra da parte degli insider. Prepararsi a una possibile inversione ribassista; interrompere acquisti long.

### Anomalia 2: Risultato senza Sforzo (Wide Spread / Low Volume)
1) **Descrizione visuale della candela**: Lo spread di prezzo è più ampio rispetto alle candele precedenti, forte direzionalità apparente.
2) **Comportamento del volume**: Volume inferiore rispetto alla candela precedente o in rapido calo.
3) **Significato (Accumulazione/Distribuzione)**: Mancanza di partecipazione. La pressione in acquisto o in vendita si sta esaurendo. Movimento "falso" non supportato dagli operatori principali (insider),.
4) **Azione da intraprendere**: Evitare l'ingresso in direzione della candela ampia. Il movimento è considerato non valido o esaurito.

### Anomalia 3: Selling Climax (Shooting Star / Upper Wick)
1) **Descrizione visuale della candela**: Candela con un'ombra (wick) superiore molto profonda e un corpo stretto situato nella parte inferiore,.
2) **Comportamento del volume**: Volumi alti o ultra-alti.
3) **Significato (Accumulazione/Distribuzione)**: Distribuzione estrema. Gli insider fanno un ultimo sforzo per liquidare l'inventario, spingendo temporaneamente i prezzi in alto per ingabbiare i trader retail rialzisti in posizioni deboli.
4) **Azione da intraprendere**: Marcare la potenziale fine di un trend rialzista. Pianificare posizioni short (vendita) alla conferma dell'inversione,.

### Anomalia 4: Stopping Volume (Hammer / Lower Wick)
1) **Descrizione visuale della candela**: Candela con un'ombra (wick) inferiore molto profonda (Hammer) e corpo stretto in alto alla fine di un trend ribassista,.
2) **Comportamento del volume**: Volumi alti o ultra-alti.
3) **Significato (Accumulazione/Distribuzione)**: Accumulazione estrema. Tutta la pressione di vendita viene assorbita dagli insider ("selling absorbed").
4) **Azione da intraprendere**: Cessare l'operatività short. Attendere la formazione del bottom e prepararsi ad aperture di posizioni long.

### Anomalia 5: Divergenza Trend/Volume
1) **Descrizione visuale della candela**: Sequenza di candele con prezzi in ascesa costante (mercato rialzista),.
2) **Comportamento del volume**: I volumi scendono progressivamente ad ogni candela,.
3) **Significato (Accumulazione/Distribuzione)**: Distribuzione latente. I mercati rialzisti sani necessitano di volume in aumento. Un volume in calo segnala una classica debolezza di fondo e l'assenza degli acquirenti principali,.
4) **Azione da intraprendere**: Mettere in sicurezza i profitti delle posizioni long. Non aprire nuove posizioni rialziste; prepararsi al ritracciamento,.

### Anomalia 6: Sumo Candle (Compressione ad Alto Volume)
1) **Descrizione visuale della candela**: Candela con spread di prezzo molto stretto (corpo e ombre contenuti) nonostante la presenza di volume comparabile o superiore alle candele precedenti. La candela appare "tozza" come un lottatore di sumo — immobile nonostante lo sforzo.
2) **Comportamento del volume**: Volume alto o pari ai massimi recenti, ma senza corrispondente movimento di prezzo.
3) **Significato (Accumulazione/Distribuzione)**: Segnale di inversione. Rappresenta "sforzo senza risultato" portato all'estremo: il prezzo non riesce a progredire perché i market maker stanno attivamente vendendo/acquistando per intrappolare i trader al dettaglio. Può essere accompagnata dal fenomeno degli 0DTE (Zero Days to Expiration) options che forza i dealer a "piazzare" i prezzi a determinati livelli tramite hedging.
4) **Azione da intraprendere**: Marcare come potenziale punto di svolta. Se la Sumo appare dopo un trend rialzista, prepararsi a short. Se appare dopo un trend ribassista, prepararsi a long. Attendere la conferma della candela successiva.

---

## Modelli Operativi 5-Minute Time Frame (Bob Volman)

### Setup: Pattern Break
* **Trigger di entrata**: Superamento di **1** pip del massimo/minimo della "signal bar" alla rottura del box/linea di confine del pattern.
* **Posizionamento dello Stop Loss**: Target fisso impostato a **10** pip di distanza dall'ingresso.
* **Condizioni di invalidazione del setup**: La chiusura della signal bar è in direzione contraria a quella del break (es. non si entra short sotto una barra rialzista, salvo rare doji/eccezioni). Si annulla se la rottura va direttamente contro una forte predominanza o in collisione con un muro dei livelli tondi (**00** o **50**),.
* **Passaggi di esecuzione**:
  1. Identificare una zona di "buildup" (compressione) prima della barriera di resistenza o supporto.
  2. Verificare che la Media Mobile a **25** periodi (25ema) sia favorevole o vicina al punto di rottura.
  3. Pre-impostare ordine limit superato di **1** pip il segnale con bracket automatico (Target: **20** pip, Stop: **10** pip).
  4. Cancellare il trade se si innesca la volatilità disordinata senza rottura netta,,.

### Setup: Pattern Break Pullback
* **Trigger di entrata**: Dopo una rottura originaria, il mercato corregge e testa dall'esterno il livello rotto (Ceiling test). Trigger scatta **1** pip oltre la fine della candela di pullback a ridosso del livello testato,,.
* **Posizionamento dello Stop Loss**: **10** pip, raccomandato stringere al di sotto dell'ultimo minimo formato durante il pullback prima dell'entrata,.
* **Condizioni di invalidazione del setup**: Il ritracciamento rientra profondamente nel pattern originario annullando la rottura, oppure la candela di segnale del pullback è eccessivamente ampia.
* **Passaggi di esecuzione**:
  1. Lasciar passare il primo Breakout senza agire.
  2. Attendere la micro-correzione (pullback) che tocca la linea tracciata (test).
  3. Controllare le chiusure delle candele: devono rispettare il confine testato (non rientrare nel pattern).
  4. Entrare in direzione del breakout originario,,.

### Setup: Pattern Break Combi
* **Trigger di entrata**: Violazione del limite di un raggruppamento (cluster) di barre formato tipicamente da una candela madre (powerbar) seguita da una o più inside bar (candele incluse). Ingresso **1** pip fuori dal massimo o minimo del combo,.
* **Posizionamento dello Stop Loss**: Standard a **10** pip, preferibilmente posizionato alla base opposta della formazione combi se compatibile,.
* **Condizioni di invalidazione del setup**: Rottura tentata prima che si generi sufficiente tensione (buildup), o la barra interna del cluster vìola anticipatamente l'estremità della powerbar,,.
* **Passaggi di esecuzione**:
  1. Identificare una candela robusta ("powerbar") seguita da un blocco laterale di contenimento (inside bar).
  2. Attendere che il raggruppamento tocchi o sfiori la EMA a **25** periodi.
  3. Piazzare ordine di entrata alla violazione dell'estremo direzionale corretto.

### Setup: Range Break (RB)
* **Trigger di entrata**: Rottura di un range orizzontale definito da almeno 2-3 tocchi di supporto e resistenza. Ingresso **1** pip oltre il confine del range sulla candela di breakout.
* **Posizionamento dello Stop Loss**: Standard a **10** pip, posizionato appena oltre il lato opposto del range.
* **Condizioni di invalidazione del setup**: La candela di breakout ha chiusura debole (wick lungo, corpo piccolo) o il range è troppo ampio (>20 pip) riducendo il rapporto rischio/rendimento.
* **Passaggi di esecuzione**:
  1. Identificare un range orizzontale ben definito con minimo 2 contatti per lato.
  2. Verificare che la 25 EMA sia piatta o in allineamento con la direzione del breakout.
  3. Attendere una barra decisiva che rompa il range con chiusura oltre il confine.
  4. Entrare alla violazione di **1** pip dall'estremo della barra di breakout.

### Setup: Inside Range Break (IRB)
* **Trigger di entrata**: Rottura di una inside bar (candela interamente contenuta nel range della candela precedente) che a sua volta è all'interno di un range più ampio. Ingresso **1** pip oltre l'estremo della inside bar.
* **Posizionamento dello Stop Loss**: Standard a **10** pip, posizionato oltre il range della barra madre.
* **Condizioni di invalidazione del setup**: La inside bar è troppo piccola (range < 3 pip) rendendo lo stop eccessivamente stretto, oppure la barra madre è troppo ampia rendendo lo stop troppo largo.
* **Passaggi di esecuzione**:
  1. Identificare una barra madre (powerbar o range bar) di dimensioni significative.
  2. Individuare una inside bar completamente contenuta nel range della barra madre.
  3. La compressione (buildup) deve essere evidente — minore è il range della inside bar, maggiore è la tensione.
  4. Entrare alla violazione di **1** pip dell'estremo della inside bar.

### Setup: Pullback Reversal
* **Trigger di entrata**: Alla fine di un rimbalzo tecnico (pullback) che incrocia la 25 EMA in trend, inserimento alla rottura del picco/minimo della doji bar o turnaround bar di inversione,.
* **Posizionamento dello Stop Loss**: Standard **10** pip protetto dalla 25 EMA,.
* **Condizioni di invalidazione del setup**: Il pullback ha ritracciato più del **60**% dello swing precedente (rendendo incerta la tendenza principale) oppure ha mostrato barre di potenza eccessiva contro-trend,.
* **Passaggi di esecuzione**:
  1. Misurare la percentuale di ritracciamento del pullback (deve essere intorno al **50**-**60**% dello swing).
  2. Verificare confluenza visiva del pullback con il tocco della EMA a **25**.
  3. Rilevare l'arresto della forza (tramite serie di candele incerte o con ombre - doji).
  4. Inserire l'ordine in direzione del trend originario,.

### Setup: Trade-for-Failure
* **Trigger di entrata**: Si avvia nella direzione OPPOSTA a un tentativo di breakout chiaramente fallito (es. bear break fallito), quando la candela in verte al rialzo. Ingresso ad **1** pip sopra o sotto la candela di inversione che deve superare di nuovo la barriera rotta in precedenza ("failure confirmation"),.
* **Posizionamento dello Stop Loss**: **10** pip standard, protetto dalla candela di falso break,.
* **Condizioni di invalidazione del setup**: L'entrata della barra di segnale si trova ancora *all'interno* del break out (non ha ri-superato la barriera invalidando il falso break). Mai anticipare il rientro nel confine del pattern,.
* **Passaggi di esecuzione**:
  1. Lasciare che il mercato effettui la falsa rottura ignorando un trend principale palese o una debolezza evidente del setup.
  2. Notare la violenta chiusura contraria al break iniziale da parte degli investitori dominanti (es. candela a forma di W-pattern middle-part).
  3. Confermare che il livello di barriera iniziale venga fisicamente oltrepassato al rientro.
   4. Entrare scommettendo sull'intrappolamento della parte perdente,,.

---

## Gestione Avanzata della Posizione (Bob Volman)

### Tipping Point Technique

Il "Tipping Point" è il livello di prezzo o comportamento di mercato che, se raggiunto, cambia la valutazione probabilistica del trade e giustifica lo spostamento dello stop a breakeven o l'uscita anticipata.

**Fasi di Gestione Post-Entrata:**

| Fase | Comportamento del Mercato | Azione |
| :--- | :------------------------- | :----- |
| Immediato post-entrata | Prezzo si muove a favore entro 1-3 barre | Mantieni la posizione; stop invariato |
| Movimento iniziale | Prezzo avanza di 4-6 pip a favore | Monitora per tipping point; valuta stop a breakeven |
| Zona di stallo | Prezzo stalla a 3-7 pip dal target, non progredisce | Sposta stop a breakeven — lo slancio iniziale è svanito |
| Inversione avversa | Prezzo inverte verso l'entrata dopo movimento favorevole | Se stop già a breakeven, accetta lo scratch (pareggio) |
| Prossimo al target | Prezzo a 8-9 pip dal target | Lascia che il trade colpisca il target di 10 pip |
| Movimento immediato avverso | Prezzo va contro dalla prima barra dopo l'entrata | Tieni lo stop al livello originale (costo del business) |

**Regola d'Oro**: Non spostare lo stop a breakeven troppo presto. Il tipping point non è una distanza fissa in pip, ma una valutazione comportamentale: il setup si sta comportando come previsto? Se l'ordine flow conferma la tesi, tieni. Se si deteriora, stringi.

### Uscite Manuali (Manual Exits)

Volman definisce 3 tipi di uscite manuali per situazioni in cui il bracket order standard (target 20 / stop 10) non è ottimale:

1. **News Report Exit**: Uscire prima di notizie macro importanti (Non-Farm Payroll, decisioni tassi, etc.). La volatilità imprevedibile e lo slippage rendono il rischio troppo alto. Chiediti: "Ne vale la pena per un target di 20 pip?" La risposta di Volman è no.

2. **Resistance Exit**: Se un trade in profitto incontra una resistenza forte e ovvia (specie in un mercato laterale), prendi profitto in anticipo. Blocca il guadagno piuttosto che restituirlo al mercato.

3. **Reversal Exit**: Se il trade è in profitto ma si forma un pattern avverso contro la tua posizione (M pattern / double top, W pattern / double bottom), esci manualmente. La pressione sta cambiando prima che il pattern si completi e cancelli il profitto.

### Adattamento a Bassa Volatilità

In condizioni di mercato a bassa volatilità, i setup standard di Volman producono meno segnali. Strategie di adattamento:

1. **Target Ridotti**: Ridurre l'obiettivo da 20 a 8-10 pip in range stretti.
2. **Tick Chart 200**: Invece del timeframe a 5 minuti, passare a un tick chart a 200 tick. I tick chart disegnano una nuova barra dopo un numero fisso di scambi, non dopo un tempo fisso. In basso volume, mantengono chiarezza visiva e producono segnali più nitidi.
3. **Filtri più stretti**: Operare solo setup con buildup molto evidente e confluenza della 25 EMA obbligatoria.
4. **Rapporto R/R adattato**: Con target ridotti, mantenere lo stop proporzionale (es. target 10, stop 5).