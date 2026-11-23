# Aggiornare l’Atlante alla v13.6

Il delta si applica al ramo `main` di [popoloni/popoloni.github.io](https://github.com/popoloni/popoloni.github.io), partendo dal commit `e4efb753f222f5fdc2264592fbf28c8e26011f83` della v13.5. I 245 file di quel commit corrispondevano ai file pubblicati su GitHub Pages al momento della verifica.

1. Apri una copia pulita del repository e controlla la versione di partenza con `git rev-parse HEAD`. Se il ramo è avanzato, applica il delta su un ramo creato dal commit indicato. Potrai così confrontare le modifiche intervenute nel frattempo.
2. Estrai il contenuto di `Knowledge_Atlas_v13_6_Delta_from_v13_5.zip` nella radice del repository. Consenti la sovrascrittura e mantieni i percorsi dell’archivio. Tutti i file della versione precedente restano presenti.
3. Dalla radice esegui `sha256sum -c SHA256SUMS.txt` (su macOS, `shasum -a 256 -c SHA256SUMS.txt`). Ogni file deve risultare valido. Il pacchetto completo contiene lo stesso albero del sito e può essere estratto in una cartella vuota.
4. Per l’anteprima esegui `python3 -m http.server 8000` e apri [il catalogo dei libri](http://localhost:8000/catalogues/volumes.html). V05 apre il libro Packt e V07 apre ESA. Da ciascun indice puoi passare da un capitolo a un tema, a una pratica o a una lettura correlata.
5. Registra e pubblica la modifica con il consueto flusso GitHub Pages. I file HTML, JSON, GraphML e i cataloghi scaricabili sono già generati.

## Riferimenti per il controllo editoriale

La [nota di versione](UPDATE_v13_6_20261123.html) elenca i libri e i temi nuovi. Il [catalogo dei 18 capitoli](catalogues/reviewed-chapters.html) riporta i numeri di pagina riferiti alle copie consultate. La [scheda storica del libro autopubblicato](catalogues/volumes/v05-h.html) conserva gli identificativi e le citazioni originarie.

Le schede distinguono i rimandi presenti nel testo, corredati di un punto di riscontro, dalle letture suggerite dall’Atlante. Il [registro delle fonti e delle relazioni](source/book_chapter_review.json) contiene anche i riferimenti EPUB di ESA. I [risultati dei controlli](verification/report.html) documentano i confronti tra i dati e la prova di navigazione.
