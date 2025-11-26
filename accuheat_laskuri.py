import streamlit as st
import pandas as pd
import numpy as np

# --- ASETUKSET JA VAKIOT ---

# Oletushinnasto (Vantaan Energia Tarkkalämpö 1.3.2025 alkaen, PDF:n ja arvioiden pohjalta)
# Huom: Alle 250 kW hinnat ovat arvioita/esimerkkejä logiikkaa varten, käyttäjä voi muokata niitä.
OLETUS_HINNASTO = {
    "Pieni": {
        "raja_min": 0, "raja_max": 249, 
        "vakio": 644.48, "teho_kerroin": 126.69  # Lähde: Hakutulos (Älykäs/Tarkkalämpö pienet)
    },
    "Keskisuuri": {
        "raja_min": 250, "raja_max": 699, 
        "vakio": 6723.59, "teho_kerroin": 25.27  # Lähde: PDF (Tarkkalämpö)
    },
    "Suuri": {
        "raja_min": 700, "raja_max": 99999, 
        "vakio": 12000.00, "teho_kerroin": 20.00 # Arvio suuren luokan skaalautuvuudesta
    }
}

def hae_hinta_parametrit(teho, hinnasto):
    """Valitsee oikean hintaluokan tehon perusteella."""
    for luokka, arvot in hinnasto.items():
        if arvot["raja_min"] <= teho <= arvot["raja_max"]:
            return arvot, luokka
    return hinnasto["Suuri"], "Suuri (Yli rajojen)"

def laske_tehokkuuskerroin(lampotila):
    """
    Laskee energiatehokkuusvaikutuksen kertoimen.
    Perustuu PDF:n pisteisiin: 30°C -> -0.4%, 40°C -> +5.6%.
    Vantaan Energian säännöissä (hakutulokset) mainitaan usein max +7% ja min -2%.
    
    Kulmakerroin: (5.6 - (-0.4)) / (40 - 30) = 0.6 %-yksikköä per aste.
    Neutraali piste (kerroin 1.0): n. 30.67 °C
    """
    # PDF:n datapisteet
    t1, eff1 = 30, -0.004
    t2, eff2 = 40, 0.056
    
    slope = (eff2 - eff1) / (t2 - t1)
    
    # Lineaarinen arvio
    vaikutus = eff1 + slope * (lampotila - t1)
    
    # Rajoitetaan Vantaan Energian tyypillisiin maksimirajoihin (-2% ... +7%)
    # Jotta laskuri ei anna epärealistisia tuloksia ääripäissä
    vaikutus = max(-0.02, min(vaikutus, 0.07))
    
    return 1.0 + vaikutus

# --- KÄYTTÖLIITTYMÄ (STREAMLIT) ---

st.set_page_config(page_title="AccuHeat Nova Säästölaskuri", layout="wide")

st.title("🔋 AccuHeat Nova - Säästölaskuri")
st.markdown("""
Tämä työkalu laskee säästöpotentiaalin Vantaan Energian kaukolämpöverkossa (Tarkkalämpö 1.3.2025).
Laskuri huomioi automaattisesti tehomaksut ja paluulämpötilan vaikutuksen.
""")

# Sivupalkki: Syötteet
st.sidebar.header("1. Kiinteistön perustiedot")
energia_vuosi = st.sidebar.number_input("Vuotuinen energiankulutus (MWh)", value=667, step=10)
asuntojen_lkm = st.sidebar.number_input("Asuntojen lukumäärä", value=68, step=1)
alv_prosentti = st.sidebar.number_input("ALV %", value=25.5, step=0.5)

st.sidebar.header("2. Nykytilanne")
teho_nyky = st.sidebar.number_input("Nykyinen laskutusteho (kW)", value=300, step=5)
paluu_nyky = st.sidebar.slider("Nykyinen paluulämpötila (°C)", 20.0, 60.0, 40.0, step=0.5)

st.sidebar.header("3. AccuHeat Nova -skenaario")
teho_alenema = st.sidebar.number_input("Tehon pieneneminen (kW)", value=40, step=1)
paluu_parannus = st.sidebar.slider("Paluulämpötilan lasku (°C)", 0.0, 20.0, 10.0, step=0.5)

# Lasketaan uudet arvot
teho_nova = teho_nyky - teho_alenema
paluu_nova = paluu_nyky - paluu_parannus

# Hinnaston asetukset (Expander, jotta ei sotke perusnäkymää)
with st.sidebar.expander("⚙️ Hinnaston lisäasetukset"):
    energiahinta = st.number_input("Energian hinta (€/MWh, alv 0)", value=33.0)
    
    st.write("**Teholuokka 250-699 kW (PDF):**")
    hinta_vakio_mid = st.number_input("Vakio-osa (€/v)", value=6723.59)
    hinta_muuttuva_mid = st.number_input("Muuttuva osa (€/kW/v)", value=25.27)
    
    # Päivitetään oletushinnastoa käyttäjän syötteillä (Keskisuuri)
    OLETUS_HINNASTO["Keskisuuri"]["vakio"] = hinta_vakio_mid
    OLETUS_HINNASTO["Keskisuuri"]["teho_kerroin"] = hinta_muuttuva_mid

# --- LASKENTALIGIIKKA ---

def laske_case(nimi, teho, paluu, energia):
    # 1. Energiamaksu
    kust_energia = energia * energiahinta
    
    # 2. Tehomaksu (haetaan oikea luokka)
    params, luokan_nimi = hae_hinta_parametrit(teho, OLETUS_HINNASTO)
    kust_teho = params["vakio"] + (params["teho_kerroin"] * teho)
    
    # 3. Välisumma
    kust_base = kust_energia + kust_teho
    
    # 4. Energiatehokkuusvaikutus
    kerroin = laske_tehokkuuskerroin(paluu)
    kust_tot_alv0 = kust_base * kerroin
    
    # 5. ALV
    kust_tot_alv = kust_tot_alv0 * (1 + alv_prosentti / 100)
    
    return {
        "Nimi": nimi,
        "Teho (kW)": teho,
        "Paluulämpö (°C)": paluu,
        "Teholuokka": luokan_nimi,
        "Energiamaksu (€)": kust_energia,
        "Tehomaksu (€)": kust_teho,
        "Tehokkuuskerroin": kerroin,
        "Summa (alv 0)": kust_tot_alv0,
        "Summa (sis. alv)": kust_tot_alv
    }

# Ajetaan laskennat
tulos_nyky = laske_case("Nykytilanne", teho_nyky, paluu_nyky, energia_vuosi)
tulos_nova = laske_case("AccuHeat Nova", teho_nova, paluu_nova, energia_vuosi)

# Lasketaan erotus
saasto_eur = tulos_nyky["Summa (sis. alv)"] - tulos_nova["Summa (sis. alv)"]
saasto_proc = (saasto_eur / tulos_nyky["Summa (sis. alv)"]) * 100

# --- TULOSTEN ESITYS ---

# Yläosan KPI-kortit
col1, col2, col3 = st.columns(3)
col1.metric("Vuosisäästö (sis. ALV)", f"{saasto_eur:,.0f} €", delta=f"{saasto_proc:.1f} %")
col2.metric("Säästö / asunto / kk", f"{(saasto_eur/asuntojen_lkm/12):.2f} €")
col3.metric("Uusi paluulämpötila", f"{paluu_nova:.1f} °C", delta=f"-{paluu_parannus:.1f} °C", delta_color="inverse")

st.divider()

# Yksityiskohtainen taulukko
st.subheader("Kustannuserittely")

df = pd.DataFrame([tulos_nyky, tulos_nova])
# Muotoillaan luvut nätimmiksi
format_dict = {
    "Energiamaksu (€)": "{:,.0f} €", 
    "Tehomaksu (€)": "{:,.0f} €", 
    "Summa (sis. alv)": "{:,.0f} €",
    "Tehokkuuskerroin": "{:.3f}"
}
st.dataframe(df.style.format(format_dict), use_container_width=True)

# Visuaalinen vertailu
st.subheader("Kustannusrakenteen vertailu")
chart_data = pd.DataFrame({
    "Kategoria": ["Energia", "Teho", "Tehokkuuslisä/hyvitys (netto)"],
    "Nykytilanne": [
        tulos_nyky["Energiamaksu (€)"], 
        tulos_nyky["Tehomaksu (€)"], 
        tulos_nyky["Summa (alv 0)"] - (tulos_nyky["Energiamaksu (€)"] + tulos_nyky["Tehomaksu (€)"])
    ],
    "Nova": [
        tulos_nova["Energiamaksu (€)"], 
        tulos_nova["Tehomaksu (€)"], 
        tulos_nova["Summa (alv 0)"] - (tulos_nova["Energiamaksu (€)"] + tulos_nova["Tehomaksu (€)"])
    ]
})

st.bar_chart(chart_data.set_index("Kategoria"))

# Selite
st.info(f"""
**Huomioita laskennasta:**
*   **Tehokkuuskerroin:** Ohjelma käyttää lineaarista mallia pisteiden 30°C (-0.4%) ja 40°C (+5.6%) välillä. Kerroin on rajoitettu välille -2% ... +7% (Vantaan Energian yleiset rajat).
*   **Nyt käytetty kerroin:** Nykytilassa **{tulos_nyky['Tehokkuuskerroin']:.3f}** ja Novan kanssa **{tulos_nova['Tehokkuuskerroin']:.3f}**.
*   **Teholuokka:** {tulos_nyky['Teholuokka']} -> {tulos_nova['Teholuokka']}. (Jos teho putoaa alle 250 kW, laskuri käyttää pienemmän kiinteistön arviohinnastoa).
""")

# Tekijänoikeus / Footer
st.caption("AccuHeat Nova Laskuri v1.0 | Perustuu Vantaan Energian 1.3.2025 hinnastotietoihin.")