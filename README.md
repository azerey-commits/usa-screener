# ABD Hisse Screener

**Filtre:** Fiyat > 5 $ ve son 30 işlem günü ortalama dolar hacmi (Kapanış × Hacim) ≥ 300 milyon $

**Kolonlar:** Fiyat · Günlük % · Bugünkü Hacim ($) · 1S Mum % · 1S SMA(100) · SMA'ya Uzaklık % · 30G Ort. $ Hacim (M)

## Kurulum (Mac)
```bash
cd usa-screener
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Çalıştırma
- Web arayüzü: `streamlit run app.py` → tarayıcıda http://localhost:8501 açılır. "Yenile" ile veriyi tazelersiniz (otomatik önbellek 10 dk).
- Terminal: `python screener.py` → tabloyu yazdırır ve CSV kaydeder. `--etf` ile ETF'ler de dahil edilir.

## Tanımlar
- **Fiyat / Günlük %:** Son günlük mumun kapanışı, bir önceki günün kapanışına göre değişim. Seans içinde bu canlı (gecikmeli) fiyattır.
- **Bugünkü Hacim ($):** Son işlem gününün dolar cinsinden hacmi (fiyat × adet). $1.25B = 1,25 milyar dolar, $850.0M = 850 milyon dolar.
- **1S Mum %:** Son 1 saatlik mumun (kapanış / açılış − 1). Seans açıkken bu mum henüz kapanmamış olabilir.
- **1S SMA(100):** Son 100 adet 1 saatlik mumun kapanış ortalaması (sadece normal seans, pre/post market hariç).
- **30G Ort. $ Hacim:** Son 30 işlem gününde günlük (kapanış × hacim) ortalaması.

## Veri kaynağı ve sınırlar
- Fiyatlar **Yahoo Finance** (yfinance kütüphanesi): ücretsiz, API anahtarı gerekmez, ~15 dk gecikmeli olabilir. Resmi bir API değildir; çok sık sorgulanırsa Yahoo geçici olarak engelleyebilir.
- Hisse listesi **Nasdaq**'ın ücretsiz screener'ından alınır (NYSE + NASDAQ + AMEX), günde bir kez önbelleğe yazılır. Ulaşılamazsa nasdaqtrader.com tam listesine düşer (daha yavaş).
- Ön eleme: Bugünkü dolar hacmi 25M $ altında olan hisseler 30 günlük kontrole hiç sokulmaz (hız için). Ortalama 300M $ olan bir hissenin bir günde 25M altına düşmesi pratikte çok nadirdir.
- İlk çalıştırma 1–3 dakika sürebilir.
