import copy
import importlib.util
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


def muodosta_hinnasto(hinta_vakio_mid: float, hinta_muuttuva_mid: float):
    """Palauttaa käyttäjän syötteillä päivitetyn hinnaston koskematta oletukseen."""

    hinnasto = copy.deepcopy(OLETUS_HINNASTO)
    hinnasto["Keskisuuri"]["vakio"] = hinta_vakio_mid
    hinnasto["Keskisuuri"]["teho_kerroin"] = hinta_muuttuva_mid
    return hinnasto

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


def laske_case(nimi, teho, paluu, energia, hinnasto, energiahinta, alv_prosentti):
    # 1. Energiamaksu
    kust_energia = energia * energiahinta

    # 2. Tehomaksu (haetaan oikea luokka)
    params, luokan_nimi = hae_hinta_parametrit(teho, hinnasto)
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
        "Summa (sis. alv)": kust_tot_alv,
    }


def muodosta_saasto_dataframe(tulos_nyky, tulos_nova):
    return pd.DataFrame(
        {
            "Säästö (€/v)": [
                tulos_nyky["Energiamaksu (€)"] - tulos_nova["Energiamaksu (€)"],
                tulos_nyky["Tehomaksu (€)"] - tulos_nova["Tehomaksu (€)"],
                tulos_nyky["Summa (alv 0)"] - tulos_nova["Summa (alv 0)"]
            ],
            "Säästö (€/kk)": [
                (tulos_nyky["Energiamaksu (€)"] - tulos_nova["Energiamaksu (€)"]) / 12,
                (tulos_nyky["Tehomaksu (€)"] - tulos_nova["Tehomaksu (€)"]) / 12,
                (tulos_nyky["Summa (alv 0)"] - tulos_nova["Summa (alv 0)"]) / 12,
            ],
        },
        index=["Energiamaksu", "Tehomaksu", "Yhteensä (alv 0)"]
    )


def muodosta_taulukko_tekstina(df: pd.DataFrame) -> str:
    """Palauttaa taulukon merkkijonona myös silloin, kun tabulate ei ole asennettuna."""

    try:
        return df.to_markdown()
    except ImportError:
        return df.to_string()


def laske_skenaariovertailu(
    energia_vuosi,
    asuntojen_lkm,
    alv_prosentti,
    teho_nyky,
    paluu_nyky,
    teho_alenema,
    paluu_parannus,
    energiahinta,
    hinta_vakio_mid,
    hinta_muuttuva_mid,
):
    teho_nova_raw = teho_nyky - teho_alenema
    teho_nova = max(teho_nova_raw, 0)
    paluu_nova = paluu_nyky - paluu_parannus

    varoitukset = []
    if teho_nova_raw < 0:
        varoitukset.append(
            "Tehon pieneneminen ylittää nykyisen tehon. Laskuri rajoitti tehon nollaan,"
            " jotta kustannukset pysyvät realistisina."
        )

    hinnasto = muodosta_hinnasto(hinta_vakio_mid, hinta_muuttuva_mid)
    tulos_nyky = laske_case(
        "Nykytilanne", teho_nyky, paluu_nyky, energia_vuosi, hinnasto, energiahinta, alv_prosentti
    )
    tulos_nova = laske_case(
        "AccuHeat Nova", teho_nova, paluu_nova, energia_vuosi, hinnasto, energiahinta, alv_prosentti
    )

    saasto_eur = tulos_nyky["Summa (sis. alv)"] - tulos_nova["Summa (sis. alv)"]
    saasto_proc = (saasto_eur / tulos_nyky["Summa (sis. alv)"]) * 100

    return {
        "tulos_nyky": tulos_nyky,
        "tulos_nova": tulos_nova,
        "saasto_eur": saasto_eur,
        "saasto_proc": saasto_proc,
        "paluu_nova": paluu_nova,
        "paluu_parannus": paluu_parannus,
        "asuntojen_lkm": asuntojen_lkm,
        "varoitukset": varoitukset,
    }


def kaynnista_sovellus():
    # --- KÄYTTÖLIITTYMÄ (STREAMLIT) ---

    import streamlit as st

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

    # Hinnaston asetukset (Expander, jotta ei sotke perusnäkymää)
    with st.sidebar.expander("⚙️ Hinnaston lisäasetukset"):
        energiahinta = st.number_input("Energian hinta (€/MWh, alv 0)", value=33.0)

        st.write("**Teholuokka 250-699 kW (PDF):**")
        hinta_vakio_mid = st.number_input("Vakio-osa (€/v)", value=6723.59)
        hinta_muuttuva_mid = st.number_input("Muuttuva osa (€/kW/v)", value=25.27)

    vertailu = laske_skenaariovertailu(
        energia_vuosi,
        asuntojen_lkm,
        alv_prosentti,
        teho_nyky,
        paluu_nyky,
        teho_alenema,
        paluu_parannus,
        energiahinta,
        hinta_vakio_mid,
        hinta_muuttuva_mid,
    )

    tulos_nyky = vertailu["tulos_nyky"]
    tulos_nova = vertailu["tulos_nova"]
    saasto_eur = vertailu["saasto_eur"]
    saasto_proc = vertailu["saasto_proc"]
    paluu_nova = vertailu["paluu_nova"]
    paluu_parannus = vertailu["paluu_parannus"]
    asuntojen_lkm = vertailu["asuntojen_lkm"]
    varoitukset = vertailu["varoitukset"]

    # --- TULOSTEN ESITYS ---

    # Yläosan KPI-kortit
    col1, col2, col3 = st.columns(3)
    col1.metric("Vuosisäästö (sis. ALV)", f"{saasto_eur:,.0f} €", delta=f"{saasto_proc:.1f} %")
    col2.metric("Säästö / asunto / kk", f"{(saasto_eur/asuntojen_lkm/12):.2f} €")
    col3.metric("Uusi paluulämpötila", f"{paluu_nova:.1f} °C", delta=f"-{paluu_parannus:.1f} °C", delta_color="inverse")

    for varoitus in varoitukset:
        st.warning(varoitus)

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

    st.subheader("Säästön erittely")
    saasto_data = muodosta_saasto_dataframe(tulos_nyky, tulos_nova)

    st.table(saasto_data.style.format("{:+,.0f} €"))

    # Visuaalinen vertailu
    st.subheader("Kustannusrakenteen vertailu")

    chart_data = pd.DataFrame(
        {
            "Nykytilanne": [
                tulos_nyky["Energiamaksu (€)"],
                tulos_nyky["Tehomaksu (€)"],
                tulos_nyky["Summa (alv 0)"],
            ],
            "Nova": [
                tulos_nova["Energiamaksu (€)"],
                tulos_nova["Tehomaksu (€)"],
                tulos_nova["Summa (alv 0)"],
            ],
        },
        index=["Energia (€/v)", "Teho (€/v)", "Yhteensä (alv 0, €/v)"],
    )

    st.bar_chart(chart_data)

    # Selite
    st.info(
        f"""
    **Huomioita laskennasta:**
    *   **Tehokkuuskerroin:** Ohjelma käyttää lineaarista mallia pisteiden 30°C (-0.4%) ja 40°C (+5.6%) välillä. Kerroin on rajoitettu välille -2% ... +7% (Vantaan Energian yleiset rajat).
    *   **Nyt käytetty kerroin:** Nykytilassa **{tulos_nyky['Tehokkuuskerroin']:.3f}** ja Novan kanssa **{tulos_nova['Tehokkuuskerroin']:.3f}**.
    *   **Teholuokka:** {tulos_nyky['Teholuokka']} -> {tulos_nova['Teholuokka']}. (Jos teho putoaa alle 250 kW, laskuri käyttää pienemmän kiinteistön arviohinnastoa).
    """
    )

    # Tekijänoikeus / Footer

    st.caption("AccuHeat Nova Laskuri v1.0 | Perustuu Vantaan Energian 1.3.2025 hinnastotietoihin.")


def aja_komentorivi_demo():
    """Mahdollistaa nopean komennolla ajettavan testin ilman Streamlitia."""

    vertailu = laske_skenaariovertailu(
        energia_vuosi=667,
        asuntojen_lkm=68,
        alv_prosentti=25.5,
        teho_nyky=300,
        paluu_nyky=40,
        teho_alenema=40,
        paluu_parannus=10,
        energiahinta=33.0,
        hinta_vakio_mid=6723.59,
        hinta_muuttuva_mid=25.27,
    )

    saasto_data = muodosta_saasto_dataframe(vertailu["tulos_nyky"], vertailu["tulos_nova"])

    print("\nKomentoajon demotulos (oletussyötteet):")
    print("Vuosisäästö (sis. ALV): {:.0f} € ({:.1f} % )".format(vertailu["saasto_eur"], vertailu["saasto_proc"]))
    print("Säästö / asunto / kk: {:.2f} €".format(vertailu["saasto_eur"] / vertailu["asuntojen_lkm"] / 12))
    print("\nSäästöerittely:")
    print(muodosta_taulukko_tekstina(saasto_data))


if __name__ == "__main__":
    # Jos skriptiä ajetaan streamlitin kautta, käynnistetään UI, muuten ajetaan kevyt demotesti
    streamlit_spec = importlib.util.find_spec("streamlit")
    run_app = False

    if streamlit_spec is not None:
        import streamlit as st
        run_app = getattr(st, "_is_running_with_streamlit", lambda: False)()

    if run_app:
        kaynnista_sovellus()
    else:
        if streamlit_spec is None:
            print("Streamlit ei ole asennettuna. Ajetaan komentorividemo.")
        aja_komentorivi_demo()
