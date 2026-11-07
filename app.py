"""Streamlit arayüzü:  streamlit run app.py"""
import pandas as pd
import streamlit as st

import screener

st.set_page_config(page_title="ABD Hisse Screener", layout="wide")
st.title("ABD Hisse Screener")
st.caption(f"Filtre: Fiyat > ${screener.MIN_PRICE:g} ve {screener.AVG_DAYS} günlük ortalama "
           f"dolar hacmi ≥ ${screener.MIN_AVG_DOLLAR_VOL/1e6:,.0f}M · Kaynak: Yahoo Finance (~15 dk gecikmeli)")

c1, c2 = st.columns([1, 5])
etf = c1.checkbox("ETF'leri dahil et", value=False)
if c1.button("Yenile", type="primary"):
    st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False)
def load(include_etf: bool) -> pd.DataFrame:
    return screener.run(include_etf=include_etf, log=lambda *_: None)


with st.spinner("Veriler indiriliyor (ilk çalıştırma 1-3 dk sürebilir)..."):
    df = load(etf)

st.write(f"**{len(df)} hisse** · son güncelleme: {pd.Timestamp.now():%H:%M:%S}")


def fmt_money(v):
    if pd.isna(v):
        return "-"
    if v >= 1e9:
        return f"${v/1e9:,.2f}B"
    return f"${v/1e6:,.1f}M"


def color(v):
    if pd.isna(v):
        return ""
    return "color: #16a34a" if v > 0 else ("color: #dc2626" if v < 0 else "")


styled = (df.style
          .format({"Fiyat": "{:,.2f}", "Günlük %": "{:+.2f}%", "Bugünkü Hacim ($)": fmt_money,
                   "1S Mum %": "{:+.2f}%", "1S SMA(100)": "{:,.2f}", "SMA'ya Uzaklık %": "{:+.2f}%",
                   "30G Ort. $ Hacim (M)": "{:,.0f}"}, na_rep="-")
          .map(color, subset=["Günlük %", "1S Mum %", "SMA'ya Uzaklık %"]))
st.dataframe(styled, width="stretch", height=700)
st.download_button("CSV indir", df.to_csv().encode("utf-8"), "screener.csv", "text/csv")
