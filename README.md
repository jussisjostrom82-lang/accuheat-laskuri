# AccuHeat Nova - Säästölaskuri

Tämä projekti sisältää Streamlit-käyttöliittymän ja komentoriviltä ajettavan demon, joilla voidaan arvioida AccuHeat Novan vaikutusta kaukolämmön teho- ja energiamaksuihin.

## Vaatimukset
- Python 3.10+ (3.11 suositeltu)
- Internet-yhteys pakettien asentamiseen (`streamlit`, `pandas`, `numpy`)

## Asennus
1. (Valinnainen) Luo virtuaaliympäristö:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Asenna riippuvuudet:
   ```bash
   pip install -r requirements.txt
   ```

## Käyttöliittymä (Streamlit)
1. Käynnistä sovellus:
   ```bash
   streamlit run accuheat_laskuri.py
   ```
2. Avaa selaimessa osoite, jonka Streamlit tulostaa (oletuksena http://localhost:8501).
3. Säädä sivupalkin syötteitä ja tarkastele säästöarvioita ja kustannuserittelyä.

## Komentoriviltä ajettava demo
Jos haluat nopean testin ilman Streamlitin graafista käyttöliittymää:
```bash
python accuheat_laskuri.py
```
Skripti tulostaa oletussyötteillä lasketut säästöt ja erittelyn. Jos Streamlit ei ole asennettuna, ohjelma ilmoittaa siitä ja ajaa silti demotulosteen.

## Nopea toimivuuden tarkistus
Voit varmistaa, että koodi on syntaktisesti kunnossa ilman UI:ta:
```bash
python -m compileall accuheat_laskuri.py
```

## Tyypilliset ongelmat
- **`ModuleNotFoundError: No module named 'streamlit'`**: Asenna riippuvuudet kohdan "Asennus" ohjeilla.
- **Portti jo varattu**: Käynnistä Streamlit eri portilla, esim. `streamlit run accuheat_laskuri.py --server.port 8502`.
