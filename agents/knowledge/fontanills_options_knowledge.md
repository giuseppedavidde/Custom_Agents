Come trader quantitativo, ecco l'analisi strutturata delle principali strategie in opzioni estratte dalle fonti, arricchita con gli esempi matematici sequenziali per ogni struttura. 

L'approccio si concentra sulla scomposizione di payoff, esposizione alle greche e calcolo rigoroso del rischio e del rendimento.

---

### 1. STRATEGIE DIREZIONALI BASE

Queste strategie forniscono un'esposizione lineare e direzionale con rischio predefinito.

**Long Call**
*   **1) Definizione e Setup:** Acquisto di un'opzione Call aspettandosi un rialzo del sottostante. 
*   **2) Condizioni di mercato ideali:** Mercato fortemente rialzista (bullish).
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Teoricamente illimitato.
    *   *Max Loss:* Limitata al premio pagato (Net Debit) moltiplicato per 100.
    *   *Breakeven:* Prezzo di Esercizio (Strike) + Premio pagato.
*   **Esempio Matematico 1:** 
    *   *Setup:* Acquisto di 1 contratto September IBM 105 Call a un premio di 5.
    *   *Calcoli:* Max Loss = $500 (5 x 100) più commissioni. Se a scadenza IBM è a 115, il profitto lordo sarà [(115 - 105) - 5] x 100 = $500. Il breakeven è a $110 (105 + 5).

---

### 2. VERTICAL SPREADS

I Vertical Spreads combinano opzioni lunghe e corte con la stessa scadenza ma strike diversi per modulare il delta e limitare il capitale a rischio.

**Bull Call Spread (Debit Spread)**
*   **1) Definizione e Setup:** Acquisto di una Call a strike inferiore e vendita di una Call a strike superiore.
*   **2) Condizioni di mercato ideali:** Mercato moderatamente rialzista.
*   **3) Calcolo del rischio:** 
    *   *Max Profit:* [(Differenza tra gli strike) - Net Debit] x 100.
    *   *Max Loss:* Net Debit pagato.
    *   *Breakeven:* Strike inferiore + Net Debit.
*   **Esempio Matematico 2:**
    *   *Setup:* Long 1 Dec Bank Index ($BKX) 90 Call @ 7.80; Short 1 Dec BKX 100 Call @ 5.00.
    *   *Calcoli:* Net Debit = 2.80 ($280). Max Risk = $280. Max Reward = [(100 - 90) - 2.80] x 100 = $720. Breakeven = 92.80 (90 + 2.80).

**Bear Put Spread (Debit Spread)**
*   **1) Definizione e Setup:** Vendita di una Put a strike inferiore e acquisto di una Put a strike superiore.
*   **2) Condizioni di mercato ideali:** Mercato ribassista. Abbassa il costo d'ingresso rispetto a una singola Put.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* [(Differenza tra gli strike) - Net Debit] x 100.
    *   *Max Loss:* Limitata al Net Debit.
    *   *Breakeven:* Strike superiore - Net Debit.
*   **Esempio Matematico 3:**
    *   *Setup:* Long 1 Oct IBM 95 Put @ 3.75; Short 1 Oct IBM 90 Put @ 2.50.
    *   *Calcoli:* Net Debit = 1.25 ($125). Max Risk = $125. Max Reward = [(95 - 90) - 1.25] x 100 = $375. Breakeven = 93.75 (95 - 1.25).

**Bull Put Spread (Credit Spread)**
*   **1) Definizione e Setup:** Vendita di una Put a strike superiore e acquisto di una Put a strike inferiore.
*   **2) Condizioni di mercato ideali:** Mercato da neutrale a rialzista. 
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Limitato al Net Credit incassato.
    *   *Max Loss:* [(Differenza tra gli strike) - Net Credit] x 100.
    *   *Breakeven:* Strike superiore - Net Credit.
*   **Esempio Matematico 4:**
    *   *Setup:* Long 1 June Bank Index ($BKX) 100 Put @ 6.75; Short 1 June BKX 110 Put @ 10.50.
    *   *Calcoli:* Net Credit incassato = 3.75 ($375). Max Reward = $375. Max Risk = [(110 - 100) - 3.75] x 100 = $625. Breakeven = 106.25 (110 - 3.75).

**Bear Call Spread (Credit Spread)**
*   **1) Definizione e Setup:** Vendita di una Call a strike inferiore e acquisto di una Call a strike superiore.
*   **2) Condizioni di mercato ideali:** Mercato da neutrale a ribassista. 
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Limitato al Net Credit incassato.
    *   *Max Loss:* [(Differenza tra gli strike) - Net Credit] x 100.
    *   *Breakeven:* Strike inferiore + Net Credit.
*   **Esempio Matematico 5:**
    *   *Setup:* Long 1 Dec IBM 90 Call @ 7.00; Short 1 Dec IBM 80 Call @ 11.50.
    *   *Calcoli:* Net Credit = 4.50 ($450). Max Reward = $450. Max Risk = [(90 - 80) - 4.50] x 100 = $550. Breakeven = 84.50 (80 + 4.50).

---

### 3. STRATEGIE DELTA NEUTRAL (NON-DIREZIONALI)

Ideate per estrarre profitto da esplosioni o contrazioni di volatilità e movimenti di grossa magnitudo, mantenendo inizialmente un Delta pari a zero.

**Long Straddle**
*   **1) Definizione e Setup:** Acquisto di una Call e di una Put ATM con lo stesso strike e medesima scadenza.
*   **2) Condizioni di mercato ideali:** Bassa volatilità iniziale con aspettativa di una forte impennata (esplosione) in qualsiasi direzione.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Illimitato al rialzo, limitato solo dallo zero del sottostante al ribasso.
    *   *Max Loss:* Costo totale delle opzioni (Total Debit).
    *   *Breakeven:* Upside = Strike + Net Debit; Downside = Strike - Net Debit.
*   **Esempio Matematico 6:**
    *   *Setup:* DELL scambia a $35.10. Long 1 Nov ATM DELL 35 Call @ 2.45; Long 1 Nov ATM DELL 35 Put @ 2.20.
    *   *Calcoli:* Total Debit = 4.65 ($465). Max Risk = $465. Upside Breakeven = 39.65 (35 + 4.65). Downside Breakeven = 30.35 (35 - 4.65).

**Long Strangle**
*   **1) Definizione e Setup:** Acquisto simultaneo di una Call OTM e di una Put OTM.
*   **2) Condizioni di mercato ideali:** Imminente esplosione di volatilità in un mercato stabile. Costa meno dello straddle ma richiede un movimento del mercato più ampio.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Teoricamente illimitato.
    *   *Max Loss:* Total Debit pagato.
    *   *Breakeven:* Upside = Call Strike + Net debit; Downside = Put Strike - Net debit.
*   **Esempio Matematico 7:**
    *   *Setup:* DELL a $35.10. Long 1 Nov DELL 40 Call @ 0.65; Long 1 Nov DELL 30 Put @ 0.70.
    *   *Calcoli:* Total Debit = 1.35 ($135). Max Risk = $135. Upside Breakeven = 41.35 (40 + 1.35). Downside Breakeven = 28.65 (30 - 1.35).

**Long Synthetic Straddle**
*   **1) Definizione e Setup:** Struttura neutrale bilanciando azioni (Delta fisso 100) con acquisto di opzioni (es. vendita di 100 azioni e acquisto di 2 Call ATM, oppure acquisto di 100 azioni e acquisto di 2 Put ATM).
*   **2) Condizioni di mercato ideali:** Movimenti estremi e bassa volatilità. Offre il vantaggio di poter aggiustare la posizione ("adjustments") al variare del mercato per tornare Delta Neutral.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Illimitato.
    *   *Max Loss:* [Net Debit opzioni + (Differenza tra prezzo acquisto azioni e strike price)] x 100.
*   **Esempio Matematico 8:**
    *   *Setup (con Put):* Long 100 Shares di DELL a $35.10; Long 2 Nov DELL 35 Puts @ 2.20.
    *   *Calcoli:* Costo Put = $440. Max Risk = [(2 x 2.20) + (35.10 - 35)] x 100 = $450. Upside Breakeven = 39.50 (35.10 + 4.40). Downside Breakeven = 30.50 {[(2 x 35) - 35.10] - 4.40}.

---

### 4. STRATEGIE PER MERCATI RANGE-BOUND (LATERALI)

Sfruttano il decadimento temporale (Theta) e la contrazione della volatilità, mantenendo rigorosamente il rischio incapsulato.

**Long Butterfly Spread**
*   **1) Definizione e Setup:** Acquisto delle due "ali" (un'opzione ITM e una OTM) e vendita simultanea del "corpo" (2 opzioni ATM), tutte dello stesso tipo.
*   **2) Condizioni di mercato ideali:** Mercato laterale (sideways) all'interno di chiari canali di supporto e resistenza.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* [(Differenza tra gli strike) - Net Debit] x 100.
    *   *Max Loss:* Limitata al Net Debit.
    *   *Breakeven:* Upside = Strike più alto - Net Debit; Downside = Strike più basso + Net Debit.
*   **Esempio Matematico 9:**
    *   *Setup:* IBM a $85. Long 1 Dec IBM 80 Call @ 7.50; Short 2 Dec IBM 85 Calls @ 5.00; Long 1 Dec IBM 90 Call @ 3.00.
    *   *Calcoli:* Net Debit = [(7.50 + 3.00) - 10.00] x 100 = $50. Max Risk = $50. Max Reward = [(85 - 80) - 0.50] x 100 = $450. Upside Breakeven = 89.50 (90 - 0.50). Downside Breakeven = 80.50 (80 + 0.50).

**Long Condor**
*   **1) Definizione e Setup:** Simile alla Butterfly, ma il "corpo" short è ripartito su due strike centrali adiacenti (acquisto di 2 ali e vendita di 2 opzioni a strike interni differenti).
*   **2) Condizioni di mercato ideali:** Mercato laterale che richiede una zona target di profittabilità ("sweet spot") più ampia rispetto alla Butterfly.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* [(Differenza tra gli strike) - Net Debit] x 100.
    *   *Max Loss:* Net Debit.
    *   *Breakeven:* Upside = Strike più alto - Net debit; Downside = Strike più basso + Net debit.
*   **Esempio Matematico 10:**
    *   *Setup:* Long 1 MSFT Dec 60 Call @ 8.00; Short 1 MSFT Dec 65 Call @ 5.00; Short 1 MSFT Dec 70 Call @ 2.00; Long 1 MSFT Dec 75 Call @ 1.00.
    *   *Calcoli:* Net Debit = [(8 + 1) - (5 + 2)] x 100 = $200. Max Risk = $200. Max Reward = [(65 - 60) - 2.00] x 100 = $300. Upside Breakeven = 73 (75 - 2). Downside Breakeven = 62 (60 + 2).

**Long Iron Butterfly**
*   **1) Definizione e Setup:** Combinazione di un Bear Call Spread e un Bull Put Spread (vendita di Call e Put ATM e acquisto di Call e Put OTM come coperture).
*   **2) Condizioni di mercato ideali:** Mercato fortemente compresso e in quiete (stabile al centro degli strike) incassato a credito.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Limitato al Net Credit incassato.
    *   *Max Loss:* [(Differenza tra gli strike short e long) - Net Credit] x 100.
    *   *Breakeven:* Upside = Short Call Strike + Net Credit; Downside = Short Put Strike - Net Credit.
*   **Esempio Matematico 11:**
    *   *Setup:* Long 1 EBAY Jan 75 Call @ 2.50; Short 1 EBAY Jan 70 Call @ 5.00; Short 1 EBAY Jan 65 Put @ 2.00; Long 1 EBAY Jan 60 Put @ 1.00.
    *   *Calcoli:* Net Credit = [(5 + 2) - (2.50 + 1)] x 100 = $350. Max Reward = $350. Max Loss = [(75 - 70) - 3.50] x 100 = $150. Upside Breakeven = 73.50 (70 + 3.50). Downside Breakeven = 61.50 (65 - 3.50).

---

### 5. RATIO SPREADS E BACKSPREADS (STRATEGIE AVANZATE NEUTRALI)

Sfruttano lo 'skew' matematico dei prezzi vendendo o comprando un numero sbilanciato di contratti.

**Ratio Call Spread**
*   **1) Definizione e Setup:** Acquisto di un'opzione a strike inferiore e vendita di un numero maggiore di opzioni (solitamente OTM) a strike superiore. 
*   **2) Condizioni di mercato ideali:** Mercato ribassista o flat in cui l'intento è incassare un credito netto pur tollerando limitati movimenti rialzisti.
*   **3) Calcolo del rischio:**
    *   *Max Profit:* [Numero contratti long x (Differenza strike + Net credit)] x 100.
    *   *Max Loss:* Illimitato al rialzo.
*   **Esempio Matematico 12:**
    *   *Setup:* Long 1 Jan QQQ 37 Call @ 2.50; Short 2 Jan QQQ 40 Calls @ 1.50.
    *   *Calcoli:* Net Credit = [(2 x 1.50) - 2.50] x 100 = $50. Max Profit = [1 x (40 - 37) + 0.50] x 100 = $350. Max Risk = Illimitato oltre l'upside breakeven. Upside Breakeven = 37 + [(3 x 2) / 1] + 0.50 = 43.50.

**Call Ratio Backspread**
*   **1) Definizione e Setup:** Vendita di Call a strike inferiore e acquisto di un numero maggiore di Call a strike superiore (spesso 1 a 2 o 2 a 3).
*   **2) Condizioni di mercato ideali:** Bassa volatilità in un mercato che sta per generare un trend esplosivo, preferibilmente al rialzo (poiché protegge al ribasso se impostato a credito).
*   **3) Calcolo del rischio:**
    *   *Max Profit:* Teoricamente illimitato al rialzo.
    *   *Max Loss:* Limitata alla zona centrale di stallo: {[(Numero short calls x differenza strike) - Net Credit] x 100}.
*   **Esempio Matematico 13:**
    *   *Setup:* Short 2 Jan QQQ 35 Calls @ 4.00; Long 3 Jan QQQ 38 Calls @ 2.25.
    *   *Calcoli:* Net Credit = [(2 x 4.00) - (3 x 2.25)] x 100 = $125. Max Profit = Illimitato (verso l'alto). Max Risk (se scade esattamente a 38) = [2 x (38 - 35) - 1.25] x 100 = $475. Upside BE = 42.75 {38 + [(3 x 2)/1] - 1.25}. Downside BE = 36.25 (35 + 1.25).
*   

In qualità di trader quantitativo, ecco un'analisi dettagliata sulla gestione della posizione (Position Management) e sulle tecniche di aggiustamento (Adjustments) per le strategie in perdita, attenendomi rigorosamente al metodo di George Fontanills e ai protocolli descritti nelle fonti. 

*(Nota preliminare: le fonti fornite non descrivono la trasformazione di una posizione specificamente in un Iron Condor o la chiusura della gamba non testata, ma codificano con precisione altre manovre di rolling, riparazione in spread/butterfly e hedging, che ti dettaglio di seguito).*

### 1. Pianificazione Pre-Trade: Stop Loss e Take Profit
Il fondamento del metodo Fontanills per azzerare l'emotività (una delle cause principali di rovina) è predefinire i livelli critici prima di entrare a mercato.

*   **La regola delle Tre Domande:** Prima di eseguire un trade, un trader deve sempre avere la risposta a tre parametri: 1) Qual è il punto di ingresso a mercato? 2) Qual è l'uscita in profitto (*Profit exit*)? 3) Qual è l'uscita in perdita (*Loss exit*)?.
*   **Loss Exit (Stop Loss):** Fissare in anticipo l'uscita in perdita equivale a definire i livelli in cui l'analisi si è dimostrata errata. Quando il prezzo tocca questo livello, l'emozione va messa da parte e l'ordine di Stop-Loss va eseguito per evitare la distruzione del capitale.
*   **Take Profit e "Cash-Out":** Non incassare è uno degli errori più frequenti. Anche se lasciar correre un profitto può sembrare vantaggioso, le fonti consigliano la tecnica del prelievo attivo. Ad esempio, è buona regola ritirare il **30% dei profitti totali** in contanti reali (riducendo permanentemente l'esposizione al rischio) e lasciare il 70% per far crescere l'account.

### 2. Gestione e Aggiustamenti Delta Neutral (Metodo Fontanills)
L'approccio avanzato prevede che una posizione in opzioni non sia semplicemente "aperta e chiusa", ma possa essere dinamicamente manipolata (Adjusted) in base alle variazioni del sottostante.

Se il mercato si muove e il tuo trade (es. un *Long Synthetic Straddle*) non è più "delta neutrale", hai solo tre possibilità: 1) Uscire dal trade, 2) Mantenere la posizione così com'è, 3) Fare un aggiustamento (*Adjustment*). 
Le tempistiche per questi aggiustamenti sono solitamente:
*   **Time-based:** Avvengono a intervalli regolari di tempo (es. ogni due settimane) per ricalibrare le greche.
*   **Event-based:** Avvengono in risposta ad eventi specifici, come annunci di utili aziendali o stravolgimenti di management.

**Esempio Matematico di Aggiustamento (Riportare a Delta 0):**
*   *Situazione iniziale:* Hai un Long Synthetic Straddle composto dall'acquisto di 100 azioni a $75 (Delta fisso +100) e l'acquisto di 2 Put ATM (Delta di circa -45 ciascuna). Il *Position Delta* iniziale è: +100 - 45 - 45 = **+10**.
*   *Movimento sfavorevole/Variazione:* Il titolo sale a $80. L'esposizione cambia: il delta delle Put crolla a -29 ciascuna. Ora il tuo Delta di posizione è sbilanciato in modo marcatamente rialzista: 100 - 29 - 29 = **+42**.
*   *Aggiustamento:* Per neutralizzare il rischio direzionale e riportare la posizione in equilibrio, compri 1 Put aggiuntiva (che aggiunge un altro -29). Il nuovo Position Delta diventa: 42 - 29 = **+13**, riportando l'equilibrio neutrale.

### 3. "Repair Strategies": Rolling e Trasformazione di posizioni in perdita
Quando una posizione direzionale si muove contro di te registrando forti perdite non realizzate, le fonti consigliano manovre matematiche chiamate *Repair Strategies* (Strategie di riparazione) per abbassare il punto di breakeven (punto di pareggio). L'efficacia di questi "salvataggi" è alta per perdite di media entità (sotto il 70%; se la perdita è oltre il 70%, spesso la riparazione è impossibile).

**Esempio Matematico: Long Call Repair in un Bull Call Spread**
*   *Il problema:* A febbraio compri una Call MSFT scadenza Luglio a strike $95, pagando un premio di $3.00. Il titolo scende sotto i $90. A causa del decadimento temporale e della perdita di valore intrinseco, la tua Call vale ora solo $1.25. Hai una perdita non realizzata di **$175** per contratto.
*   *La riparazione (Rolling Down):* Imposti un "roll down" per convertire la singola posizione in un *Bull Call Spread*. Immetti un ordine per vendere 2 Call Luglio a strike 95 per $1.25 ciascuna (andando short di un contratto, coprendo il tuo) e compri 1 Call Luglio a strike 90 per $2.90.
*   *Il Risultato:* Questa conversione aggiunge solo un modesto rischio di capitale netto, ma *abbassa drasticamente il tuo Breakeven da $98.00 a $93.25*, aumentandoti le probabilità matematiche di tornare in profitto o pareggiare se il trend inverte leggermente.

**Esempio Matematico: Trasformazione in un Butterfly Spread**
*   *Alternativa di riparazione:* Con la stessa posizione in perdita (titolo a 90, possiedi 1 Call 95), puoi trasformare tutto in una *Traditional Butterfly*. Vendi 2 Call Luglio 90 a $4.00 l'una, mantieni la tua Call 95 originale, e compri 1 Call Luglio 85 per $7.30.
*   *Il Risultato:* Il rischio totale al ribasso viene ridotto a un debito di $230, il rischio al rialzo è strettamente limitato, e anche se il titolo si ferma in un mercato range-bound e non esplode, il trade andrà comunque in profitto al centro delle ali.

### 4. Hedging passivo: Lo "Unwinding" e le protezioni per Short Call
Quando è in corso una grave crisi direzionale, le fonti documentano due ulteriori pratiche di contenimento del rischio:

*   **Unwind the Position (Sbrogliare/liquidare):** Se la posizione è stata usata per fare hedging incrociato e le cose vanno male, "unwinding" significa chiudere del tutto la gamba difensiva o la struttura intera. Questo approccio è raccomandato se il sottostante scambia *sotto* il punto di pareggio e si vuole mantenere il titolo fisico in attesa di tempi migliori; se lo si fa al di sopra del breakeven, il costo per lo smontaggio comporta un prelievo negativo netto.
*   **Delta Hedge su Short Trades:** Se sei in perdita su una posizione di "Short Call" scoperta, le fonti indicano di proteggersi shortando l'azione fisica. Vendi pacchetti del sottostante e inizi ad "acquistare" piccole frazioni in caso di ritracciamenti e "vendere" ulteriormente se il mercato riprende in salita, in modo da creare un *rapporto di copertura statico* ("static hedge ratio") che congela la perdita causata dalla Short Call originaria. L'alternativa suggerita per difendersi è trasformarla in uno *Synthetic Short*, vendendo una Call ATM e comprando una Put ATM.
*   

Le fonti forniscono regole molto rigorose basate sulle Greche e sulla Volatilità, utili per ottimizzare il rapporto rischio/rendimento e per selezionare i parametri numerici ideali di ingresso a mercato. Ecco la sintesi delle regole pratiche e dei parametri numerici fondamentali:

### 1. Regole pratiche basate sulle Greche

**Delta (Direzionalità e Probabilità)**
*   **Regola:** Il Delta non indica solo di quanto cambierà il prezzo dell'opzione rispetto al sottostante, ma rappresenta anche la probabilità statistica che l'opzione scada In-The-Money (ITM),. 
*   **Delta Neutrality:** Per neutralizzare il rischio direzionale, la somma totale dei Delta di una posizione (Position Delta) deve essere bilanciata a zero (es. possedere 100 azioni fisiche a Delta +100 e comprare 2 Put ATM a Delta -50),.

**Gamma (Accelerazione del Delta)**
*   **Regola:** Il Gamma misura la velocità con cui il Delta cambia al variare del sottostante. Se non si desidera che la propria posizione (soprattutto in strategie delta-neutrali) venga esposta a forti oscillazioni a causa di un movimento improvviso del mercato, è essenziale monitorare e gestire il Gamma.

**Theta (Decadimento Temporale)**
*   **Regola:** Le opzioni sono asset deperibili ("wasting assets") e il Theta misura quanto valore estrinseco perdono ogni giorno,. Il decadimento temporale non è lineare, ma **accelera drasticamente negli ultimi 30 giorni di vita** dell'opzione.

**Vega (Sensibilità alla Volatilità)**
*   **Regola:** Il Vega indica di quanto cambia il prezzo dell'opzione in base a una variazione percentuale della Volatilità Implicita (IV). Anche se il sottostante rimane fermo, un picco di volatilità farà aumentare il valore dell'opzione tramite l'effetto Vega.

### 2. Regole pratiche sulla Volatilità (Storica e Implicita)

*   **Ritorno alla Media (Mean Reversion):** La volatilità implicita si comporta come un elastico: raggiunge estremi ma tende sempre a tornare verso il suo livello medio.
*   **Quando Comprare:** Le opzioni lunghe (long calls/long puts) vanno acquistate quando l'IV è **storicamente bassa**, anticipando un'esplosione di volatilità che farà aumentare il premio indipendentemente dalla direzione,.
*   **Quando Vendere:** Le opzioni vanno vendute (creando strategie a credito) quando l'IV è **molto alta**, speculando su una sua contrazione.
*   **Evitare il "Volatility Crush":** Non comprare mai opzioni subito prima di un annuncio atteso (es. utili aziendali) se l'IV è già salita alle stelle. Dopo l'annuncio, la volatilità crollerà (volatility crush) e l'opzione perderà valore drammaticamente, causando perdite anche se si è indovinata la direzione del prezzo. 

### 3. Parametri Numerici Ideali per l'Ingresso a Mercato

Le fonti specificano requisiti numerici chiari per filtrare le operazioni, scartare i trade tossici e massimizzare le probabilità di successo:

**Timing e Scadenze (Regola del 90 / 30)**
*   **Ingresso (Acquisto):** Per mitigare gli effetti negativi del Theta, comprare sempre opzioni che abbiano **almeno 90 giorni** rimanenti alla scadenza.
*   **Uscita/Gestione:** Non detenere opzioni lunghe quando mancano **meno di 30 giorni** alla scadenza, a meno che non si stia chiudendo la posizione, poiché l'accelerazione del decadimento temporale distruggerà il capitale.

**Filtri di Liquidità (Regola del 300k / 100)**
*   **Azioni sottostanti:** Scartare azioni che scambiano un volume inferiore a **300.000 azioni al giorno** per evitare slippage e spread denaro/lettera eccessivi,.
*   **Opzioni:** Assicurarsi che i contratti di opzione selezionati abbiano un Open Interest di **almeno 100 contratti**.

**Target di Delta per la selezione degli Strike**
*   **Opzioni At-The-Money (ATM):** Hanno storicamente un Delta prossimo a **50** (50% di probabilità di finire ITM) e offrono la maggiore liquidità e spread più stretti,.
*   **Opzioni Out-Of-The-Money (OTM) profonde:** Hanno un Delta tra **10 e 15**, indicando solo un 10-15% di probabilità di successo alla scadenza (comparate all'acquisto di un biglietto della lotteria). 
*   **Sostituzione dell'azione (Stock Replacement):** Se si vuole replicare un'azione impiegando meno capitale, acquistare opzioni Deep In-The-Money (spesso LEAPS) con un Delta pari o prossimo a **90**, poiché si muoveranno quasi punto su punto (0,90$) per ogni dollaro mosso dal sottostante.

**Momentum e Prezzo**
*   **Identificare i Trend:** Un movimento giornaliero del prezzo pari o superiore al **20%** rispetto al giorno precedente è l'indicatore chiave per certificare un forte "momentum" (rialzista o ribassista) su cui operare.
*   **Approccio Contrarian:** Per strategie di inversione, cercare azioni che abbiano subito un crollo di magnitudo pari o superiore al **50%** (Blow-off bottom), che segnalano potenziale esaurimento dei venditori (capitulation) e un imminente rimbalzo,. 
*   **Prezzo base:** Titoli che scambiano sotto i **$20** sono considerati ideali per sfruttare una leva maggiore nei movimenti percentuali, mentre per le azioni sopra i **$25** gli strike price sono generalmente scanditi a intervalli di **$5**.