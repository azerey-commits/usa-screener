"""
ABD hisse screener'ı
--------------------
Filtreler:
  * Fiyat > 5 USD
  * Son 30 işlem günü ortalama dolar hacmi (Kapanış x Hacim) >= 300 Milyon USD

Kolonlar:
  Sembol (TradingView linki), Şirket, Endüstri, Sektör,
  Fiyat, Günlük %, Bugünkü Hacim ($), 30G Ort. $ Hacim, 1S Mum %, 1S SMA(100), SMA'ya Uzaklık %,
  52H En Yüksek / Uzaklık %, 52H En Düşük / Uzaklık %

Veri kaynağı: Yahoo Finance (yfinance) + Nasdaq hisse listesi. Ücretsiz, API anahtarı gerekmez.
Kullanım:  python screener.py            (tablo yazdırır ve CSV kaydeder)
           python screener.py --etf      (ETF'leri de dahil et)
"""
from __future__ import annotations

import argparse
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

MIN_PRICE = 5.0
MIN_AVG_DOLLAR_VOL = 300_000_000
AVG_DAYS = 30
SMA_LEN = 100
CHUNK = 150  # yfinance tek seferde indirilen sembol sayısı

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
CACHE_DIR = Path(__file__).with_name(".cache")


# ---------------------------------------------------------------- evren (universe)
def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _to_yahoo(sym: str) -> str:
    # BRK/B, BRK.B  ->  BRK-B  (Yahoo formatı)
    return sym.strip().replace("/", "-").replace(".", "-").replace("^", "-P")


_NAME_JUNK = re.compile(
    r"\s+(Class [A-C] )?(Common Stock|Ordinary Shares?|Common Shares|American Depositary Shares?|"
    r"ADS|Depositary Shares?|Shares of Beneficial Interest).*$", re.I)


def _clean_name(n: str) -> str:
    return _NAME_JUNK.sub("", str(n or "")).strip()


def universe_from_nasdaq_screener(include_etf: bool) -> dict[str, dict]:
    """Nasdaq'ın ücretsiz screener API'si: tüm NYSE/NASDAQ/AMEX hisseleri; son fiyat, hacim,
    şirket adı ve endüstri ile. Fiyat/hacim sadece kaba ön eleme için kullanılır
    (fiyat > 5 ve bugünkü $ hacim >= 25M); kesin filtre yfinance'ın 30 günlük verisiyle yapılır."""
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&download=true"
    data = json.loads(_get(url))
    rows = data["data"]["rows"]
    out: dict[str, dict] = {}
    for r in rows:
        try:
            price = float(str(r["lastsale"]).replace("$", "").replace(",", ""))
            vol = float(str(r["volume"]).replace(",", ""))
        except (ValueError, KeyError, TypeError):
            continue
        if price > MIN_PRICE and price * vol >= 25_000_000:
            out[_to_yahoo(r["symbol"])] = {"name": _clean_name(r.get("name")),
                                           "industry": (r.get("industry") or "").strip(),
                                           "sector": (r.get("sector") or "").strip()}
    if include_etf:
        url = "https://api.nasdaq.com/api/screener/etf?tableonly=true&limit=25000&download=true"
        try:
            d = json.loads(_get(url))
            rows = d["data"].get("data", {}).get("rows") or d["data"].get("rows") or []
            for r in rows:
                if r.get("symbol"):
                    out[_to_yahoo(r["symbol"])] = {"name": (r.get("companyName") or "").strip(),
                                                   "industry": "ETF", "sector": "ETF"}
        except Exception:
            pass
    return out


def universe_from_nasdaqtrader(include_etf: bool) -> dict[str, dict]:
    """Yedek yöntem: Nasdaq Trader sembol dizini (tüm ABD borsalarında işlem gören semboller).
    Ön eleme yok, bu yüzden daha yavaş (~10k sembol). Endüstri bilgisi yok (sonradan yfinance'tan)."""
    raw = _get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt").decode()
    df = pd.read_csv(io.StringIO(raw), sep="|")
    df = df[df["Nasdaq Traded"] == "Y"]
    df = df[df["Test Issue"] == "N"]
    if not include_etf:
        df = df[df["ETF"] == "N"]
    df = df.dropna(subset=["Symbol"])
    sym = df["Symbol"].astype(str)
    # warrant / unit / right / preferred gibi türevleri ele
    df = df[~sym.str.contains(r"[\$\.\^]|\s", regex=True) | sym.str.match(r"^[A-Z]+\.[A-B]$")]
    return {_to_yahoo(r["Symbol"]): {"name": _clean_name(r["Security Name"]),
                                     "industry": "ETF" if r["ETF"] == "Y" else "",
                                     "sector": "ETF" if r["ETF"] == "Y" else ""}
            for _, r in df.iterrows()}


def get_universe(include_etf: bool = False) -> dict[str, dict]:
    """{sembol: {name, industry, sector}} döner; günde bir kez önbelleğe yazılır."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / f"universe2_{'etf' if include_etf else 'stk'}_{datetime.now():%Y%m%d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        uni = universe_from_nasdaq_screener(include_etf)
        if len(uni) < 100:
            raise RuntimeError("liste çok kısa")
    except Exception as e:
        print(f"[uyarı] Nasdaq screener API kullanılamadı ({e}); tam liste ile devam ediliyor.")
        uni = universe_from_nasdaqtrader(include_etf)
    cache.write_text(json.dumps(uni))
    return uni


def fill_missing_info(uni: dict[str, dict], tickers: list[str]) -> None:
    """Adı veya endüstrisi eksik olanları yfinance'tan tamamlar (kalıcı önbellekli)."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_f = CACHE_DIR / "info.json"
    try:
        cache = json.loads(cache_f.read_text())
    except Exception:
        cache = {}
    missing = [t for t in tickers if not (uni.get(t, {}).get("name") and uni.get(t, {}).get("industry"))]
    todo = [t for t in missing if t not in cache]

    def fetch(t):
        try:
            i = yf.Ticker(t).info
            return t, {"name": i.get("shortName") or i.get("longName") or "",
                       "industry": i.get("industry") or ("ETF" if i.get("quoteType") == "ETF" else ""),
                       "sector": i.get("sector") or ""}
        except Exception:
            return t, None

    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for t, info in ex.map(fetch, todo):
                if info:
                    cache[t] = info
        try:
            cache_f.write_text(json.dumps(cache))
        except Exception:
            pass
    for t in missing:
        if t in cache:
            cur = uni.setdefault(t, {})
            for k, v in cache[t].items():
                if v and not cur.get(k):
                    cur[k] = v


def tradingview_url(sym: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=" + sym.replace("-", ".")


# ---------------------------------------------------------------- veri indirme
def _download(tickers: list[str], **kw) -> dict[str, pd.DataFrame]:
    """yfinance'tan parça parça indirir, {sembol: OHLCV DataFrame} döner."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK):
        part = tickers[i:i + CHUNK]
        for attempt in range(3):
            try:
                df = yf.download(part, group_by="ticker", auto_adjust=False, threads=True,
                                 progress=False, **kw)
                break
            except Exception:
                time.sleep(2 * (attempt + 1))
        else:
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            for t in part:
                if t in df.columns.get_level_values(0):
                    sub = df[t].dropna(how="all")
                    if not sub.empty:
                        out[t] = sub
        else:  # tek sembol
            out[part[0]] = df.dropna(how="all")
    return out


# ---------------------------------------------------------------- hesaplamalar
def daily_metrics(d: pd.DataFrame) -> dict | None:
    d = d.dropna(subset=["Close", "Volume"])
    if len(d) < AVG_DAYS + 1:
        return None
    last, prev = d.iloc[-1], d.iloc[-2]
    dollar_vol = (d["Close"] * d["Volume"]).iloc[-AVG_DAYS:]
    return {
        "Fiyat": float(last["Close"]),
        "Günlük %": (float(last["Close"]) / float(prev["Close"]) - 1) * 100,
        "Bugünkü Hacim ($)": float(last["Close"]) * float(last["Volume"]),
        "30G Ort. $ Hacim (M)": float(dollar_vol.mean()) / 1e6,
        "Tarih": d.index[-1].strftime("%Y-%m-%d"),
    }


def hourly_metrics(h: pd.DataFrame) -> dict:
    h = h.dropna(subset=["Open", "Close"])
    if h.empty:
        return {}
    last = h.iloc[-1]
    sma = h["Close"].rolling(SMA_LEN).mean().iloc[-1] if len(h) >= SMA_LEN else float("nan")
    res = {
        "1S Mum %": (float(last["Close"]) / float(last["Open"]) - 1) * 100,
        "1S SMA(100)": float(sma),
        "Son 1S Mum": h.index[-1].strftime("%m-%d %H:%M"),
    }
    res["SMA'ya Uzaklık %"] = (float(last["Close"]) / sma - 1) * 100 if sma == sma else float("nan")
    return res


def yearly_metrics(d: pd.DataFrame, price: float) -> dict:
    """52 haftalık en yüksek / en düşük (gün içi High/Low) ve fiyatın bunlara uzaklığı."""
    d = d.dropna(subset=["High", "Low"])
    if d.empty:
        return {}
    hi, lo = float(d["High"].max()), float(d["Low"].min())
    return {
        "52H En Yüksek": hi,
        "52H Yükseğe Uzaklık %": (price / hi - 1) * 100,
        "52H En Düşük": lo,
        "52H Düşüğe Uzaklık %": (price / lo - 1) * 100,
    }


def run(include_etf: bool = False, log=print) -> pd.DataFrame:
    t0 = time.time()
    uni = get_universe(include_etf)
    syms = sorted(uni)
    log(f"Evren: {len(syms)} sembol. Günlük veriler indiriliyor...")
    daily = _download(syms, period="3mo", interval="1d")

    rows = {}
    for t, d in daily.items():
        m = daily_metrics(d)
        if m and m["Fiyat"] > MIN_PRICE and m["30G Ort. $ Hacim (M)"] * 1e6 >= MIN_AVG_DOLLAR_VOL:
            rows[t] = m
    log(f"Filtreyi geçen: {len(rows)} hisse. 1 saatlik veriler indiriliyor...")

    hourly = _download(list(rows), period="60d", interval="1h", prepost=False)
    for t in rows:
        if t in hourly:
            rows[t].update(hourly_metrics(hourly[t]))

    log("52 haftalık veriler indiriliyor...")
    yearly = _download(list(rows), period="1y", interval="1d")
    for t in rows:
        if t in yearly:
            rows[t].update(yearly_metrics(yearly[t], rows[t]["Fiyat"]))

    log("Şirket bilgileri tamamlanıyor...")
    fill_missing_info(uni, list(rows))
    for t in rows:
        info = uni.get(t, {})
        rows[t].update({"Şirket": info.get("name", ""), "Endüstri": info.get("industry", ""),
                        "Sektör": info.get("sector", ""), "TradingView": tradingview_url(t)})

    cols = ["Şirket", "Endüstri", "Sektör", "Fiyat", "Günlük %", "Bugünkü Hacim ($)", "1S Mum %", "1S SMA(100)",
            "SMA'ya Uzaklık %", "52H En Yüksek", "52H Yükseğe Uzaklık %", "52H En Düşük",
            "52H Düşüğe Uzaklık %", "30G Ort. $ Hacim (M)", "Son 1S Mum", "Tarih", "TradingView"]
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=cols)
    df.index.name = "Sembol"
    df = df.sort_values("30G Ort. $ Hacim (M)", ascending=False)
    log(f"Bitti ({time.time() - t0:.0f} sn).")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--etf", action="store_true", help="ETF'leri de dahil et")
    args = ap.parse_args()
    res = run(include_etf=args.etf)
    pd.set_option("display.width", 200, "display.max_rows", 500)
    print(res.round(2).to_string())
    out = Path(__file__).with_name(f"screener_{datetime.now():%Y%m%d_%H%M}.csv")
    res.round(4).to_csv(out)
    print(f"\nCSV kaydedildi: {out}")
