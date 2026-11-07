"""Streamlit arayüzü:  streamlit run app.py"""
import pandas as pd
import streamlit as st

import screener

st.set_page_config(page_title="ABD Hisse Screener", layout="wide")
st.title("ABD Hisse Screener")
st.caption(f"Temel filtre: Fiyat > ${screener.MIN_PRICE:g} ve {screener.AVG_DAYS} günlük ortalama "
           f"dolar hacmi ≥ ${screener.MIN_AVG_DOLLAR_VOL/1e6:,.0f}M · Kaynak: Yahoo Finance (~15 dk gecikmeli)")

c1, c2 = st.columns([1, 5])
etf = c1.checkbox("ETF'leri dahil et", value=False)
if c1.button("Yenile", type="primary"):
    st.cache_data.clear()


DATA_VERSION = 4  # kolon yapısı değişince artır: eski önbellek kullanılmaz


@st.cache_data(ttl=600, show_spinner=False)
def load(include_etf: bool, version: int) -> pd.DataFrame:
    return screener.run(include_etf=include_etf, log=lambda *_: None)


with st.spinner("Veriler indiriliyor (ilk çalıştırma 1-3 dk sürebilir)..."):
    df = load(etf, DATA_VERSION)

# ------------------------------------------------------------------ filtre paneli
# Dolar cinsinden kolonlarda filtre milyon $ (M$) olarak girilir.
MONEY_COLS = {"Bugünkü Hacim ($)": 1e6}
num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _opts(col):
    return sorted(x for x in df[col].dropna().unique() if x) if col in df.columns else []


with st.expander("Filtreler", expanded=True):
    t1, t2, t3 = st.columns([2, 2, 3])
    sym_q = t1.text_input("Sembol / şirket ara (virgülle birden fazla: AAPL, nvidia)", "")
    sectors = t2.multiselect("Sektör", _opts("Sektör"))
    industries = t3.multiselect("Endüstri", _opts("Endüstri"))
    grid = st.columns(4)
    bounds = {}
    for i, col in enumerate(num_cols):
        scale = MONEY_COLS.get(col, 1)
        label = "Bugünkü Hacim (milyon $)" if col in MONEY_COLS else col
        with grid[i % 4]:
            st.markdown(f"**{label}**".replace("$", "\\$"))
            a, b = st.columns(2)
            lo = a.number_input("Min", value=None, key=f"min_{col}", format="%.2f",
                                placeholder="min", label_visibility="collapsed")
            hi = b.number_input("Max", value=None, key=f"max_{col}", format="%.2f",
                                placeholder="max", label_visibility="collapsed")
            bounds[col] = (lo, hi, scale)
    if st.button("Filtreleri temizle"):
        for col in num_cols:
            st.session_state.pop(f"min_{col}", None)
            st.session_state.pop(f"max_{col}", None)
        st.rerun()

view = df
if sym_q.strip():
    wanted = [w.strip().upper() for w in sym_q.split(",") if w.strip()]
    hay = view.index.to_series().str.upper() + " " + view.get("Şirket", "").fillna("").str.upper()
    view = view[hay.apply(lambda x: any(w in x for w in wanted))]
if sectors:
    view = view[view["Sektör"].isin(sectors)]
if industries:
    view = view[view["Endüstri"].isin(industries)]
for col, (lo, hi, scale) in bounds.items():
    if lo is not None:
        view = view[view[col] >= lo * scale]
    if hi is not None:
        view = view[view[col] <= hi * scale]

st.write(f"**{len(view)} / {len(df)} hisse** · son güncelleme: {pd.Timestamp.now():%H:%M:%S}")


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


pct_cols = [c for c in ["Günlük %", "1S Mum %", "SMA'ya Uzaklık %", "52H Yükseğe Uzaklık %",
                         "52H Düşüğe Uzaklık %"] if c in view.columns]
fmt = {c: "{:+.2f}%" for c in pct_cols}
fmt.update({"Fiyat": "{:,.2f}", "Bugünkü Hacim ($)": fmt_money, "1S SMA(100)": "{:,.2f}",
            "52H En Yüksek": "{:,.2f}", "52H En Düşük": "{:,.2f}", "30G Ort. $ Hacim (M)": "{:,.0f}"})
fmt = {k: v for k, v in fmt.items() if k in view.columns}
# Sembol kolonu TradingView linki olarak gösterilir (tıklayınca grafik açılır)
show = view.copy()
if "TradingView" in show.columns:
    links = show.pop("TradingView")
else:
    links = "https://www.tradingview.com/chart/?symbol=" + show.index.str.replace("-", ".")
show.insert(0, "Sembol", links)
show = show.reset_index(drop=True)

styled = show.style.format(fmt, na_rep="-").map(color, subset=pct_cols)
st.dataframe(
    styled, width="stretch", height=700, hide_index=True,
    column_config={
        "Sembol": st.column_config.LinkColumn("Sembol", display_text=r"symbol=(.*)$", pinned=True,
                                              help="Tıkla: TradingView'da aç"),
        "Şirket": st.column_config.TextColumn("Şirket", pinned=True),
    },
)
st.download_button("CSV indir", view.to_csv().encode("utf-8"), "screener.csv", "text/csv")
