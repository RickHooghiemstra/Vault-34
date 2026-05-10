#!/usr/bin/env python3
"""
Build GAA_Akra_Validation_100.xlsx and GAA_Akra_Shopify_100.csv
from verified search-harvest data for 100 Akrapovič products on uitlaatstore.nl.
Note: uitlaatstore.nl uses strict IP-allowlist blocking (x-deny-reason: host_not_allowed)
so prices were harvested from Google search snippets and cross-referenced with
motordempers.nl / fc-moto.de reference data. Items with unconfirmed prices are
flagged MANUAL_REVIEW_PRICE.
"""

import csv
import re
import pandas as pd
from decimal import Decimal, ROUND_DOWN

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
VAT_DIVISOR   = Decimal("1.21")
MULTIPLIER    = Decimal("1.34")
WEIGHT_DEFAULT = "5000"          # grams  (5 kg)
VENDOR        = "Akrapovič"
SHOPIFY_CAT   = (
    "Vehicles & Parts > Vehicle Parts & Accessories > "
    "Motor Vehicle Parts > Motor Vehicle Exhaust Systems"
)
BASE_URL = "https://www.uitlaatstore.nl"

SHOPIFY_HEADERS = [
    "Handle","Title","Body (HTML)","Vendor","Product Category","Type","Tags",
    "Published","Option1 Name","Option1 Value","Variant SKU","Variant Grams",
    "Variant Inventory Tracker","Variant Inventory Qty","Variant Inventory Policy",
    "Variant Fulfillment Service","Variant Price","Variant Compare At Price",
    "Variant Requires Shipping","Variant Taxable","Image Src","Image Position",
    "Image Alt Text","SEO Title","SEO Description","Status","Standard Product Type",
]

# ---------------------------------------------------------------------------
# master product list — 100 items
# (title, sku, brand, model, years, retail_incl_vat, url_slug, line_type, material)
# retail_incl_vat = None → MANUAL_REVIEW_PRICE
# ---------------------------------------------------------------------------
PRODUCTS = [
    # --- Yamaha ---
    ("Akrapovič Racing Line (Titanium) Yamaha MT-09/FZ-09 2014-2020",
     "S-Y9R8-HEGEHT","Yamaha","MT-09","2014-2020",1769.00,
     "s-y9r8-hegeht-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Yamaha MT-07/FZ-07 2014-2020",
     "S-Y7R1-HAFT","Yamaha","MT-07","2014-2020",1425.00,
     "s-y7r1-haft-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Racing Line (Carbon) Yamaha MT-07/FZ-07 2014-2020",
     "S-Y7R2-AFC","Yamaha","MT-07","2014-2020",1629.00,
     "s-y7r2-afc-akrapovic-racing-line-carbon","Racing Line","Carbon"),
    ("Akrapovič Racing Line (Carbon) Yamaha MT-09 2021-2025",
     "S-Y9R12-APC","Yamaha","MT-09","2021-2025",None,
     "s-y9r12-apc-akrapovic-racing-line-carbon","Racing Line","Carbon"),
    ("Akrapovič Racing Line Carbon Uitlaatsysteem Yamaha MT-09 2021-2025",
     "S-Y9R18-APC","Yamaha","MT-09","2021-2025",None,
     "s-y9r18-apc-akrapovic-racing-line-kit-carbon-1","Racing Line","Carbon"),
    ("Akrapovič Racing Line RVS Volledig Uitlaatsysteem Yamaha MT-09 2025-2026",
     "S-Y9R-MT09-2526","Yamaha","MT-09 / Tracer 9","2025-2026",None,
     "akrapovic-racing-line-rvs-volledig-uitlaatsysteem-ekeur-yamaha-mt-09-2025-2026-tracer9-gt-gt",
     "Racing Line","Stainless Steel"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha MT-10/FZ-10 2016-2020",
     "S-Y10SO15-HAPT","Yamaha","MT-10","2016-2020",None,
     "s-y10so15-hapt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha XT1200Z/E 2010-2020",
     "S-Y12SO2-HAAT","Yamaha","XT1200Z","2010-2020",None,
     "s-y12so2-haat-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha FJR 1300 2013-2020",
     "S-Y13SO3-HT","Yamaha","FJR 1300","2013-2020",None,
     "s-y13so3-ht-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Yamaha TMAX 2020-2024",
     "S-Y5R8-HILT","Yamaha","TMAX","2020-2024",None,
     "s-y5r8-hilt-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha R3 2022",
     "S-Y3SO6-IVOSS","Yamaha","YZF-R3","2022",395.00,
     "akrapovic-s-y3so6-ivoss","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) Yamaha MT-03/R3 2022",
     "S-Y3SO3-HRSS","Yamaha","MT-03","2022",578.00,
     "akrapovic-s-y3so3-hrss","Slip-on Line","Carbon"),
    ("Akrapovič Racing Line (Carbon) Yamaha YZF-R25",
     "S-Y3R1-APC","Yamaha","YZF-R25","2014-2020",None,
     "s-y3r1-apc-akrapovic-racing-line-carbon","Racing Line","Carbon"),
    ("Akrapovič Racing Line (Titanium) Yamaha MT-125 2014-2019",
     "S-Y125R4-HRT","Yamaha","MT-125","2014-2019",None,
     "s-y125r4-hrt-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Yamaha MT-125 2021-2022",
     "S-Y125R2-HRT","Yamaha","MT-125","2021-2022",849.00,
     "s-y125r2-hrt-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha XSR 125 2021-2025",
     "S-Y125R10-HBFGT","Yamaha","XSR 125","2021-2025",849.00,
     "s-y125r10-hbfgt","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha YZF-R125 / MT-125 2019-2022",
     "S-Y125R8-HZT","Yamaha","YZF-R125","2019-2022",None,
     "akrapovic-s-y125r8-hzt","Slip-on Line","Titanium"),

    # --- BMW ---
    ("Akrapovič Slip-on Line (Titanium) BMW R 1250 RT 2019-2023",
     "S-B12SO21-HALAGT","BMW","R 1250 RT","2019-2023",None,
     "s-b12so21-halagt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW R 1250 R 2019-2023",
     "S-B12SO22-HALAGTBL","BMW","R 1250 R","2019-2023",None,
     "s-b12so22-halagtbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW R 1250 GS/Adventure 2019-2021",
     "S-B12SO23-HAATBL","BMW","R 1250 GS","2019-2021",None,
     "s-b12so23-haatbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW R 1300 GS/Adventure 2024-2026",
     "S-B13SO1-HAATBL","BMW","R 1300 GS","2024-2026",969.00,
     "akrapovic-slip-on-line-titanium-bmw-r1300gs-2024","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW R NINET 2014-2023",
     "S-B12SO17-HBRBL","BMW","R nineT","2014-2023",None,
     "s-b12so17-hbrbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW F 750 GS 2018-2023",
     "S-B8SO8-HFBFCTBL","BMW","F 750 GS","2018-2023",None,
     "s-b8so8-hfbfctbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) BMW F 900 R 2020-2023",
     "S-B9SO2-APC","BMW","F 900 R","2020-2023",930.00,
     "s-b9so2-apc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Evolution Line (Titanium) BMW S 1000 RR 2019-2023",
     "S-B10E9-APLT","BMW","S 1000 RR","2019-2023",None,
     "s-b10e9-aplt-akrapovic-evolution-line-titanium","Evolution Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW S 1000 RR 2019-2023",
     "S-B10SO11-CBT","BMW","S 1000 RR","2019-2023",None,
     "s-b10so11-cbt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) BMW S 1000 R 2021-2023",
     "S-B10SO16-HZC","BMW","S 1000 R","2021-2023",None,
     "akrapovic-s-b10so16-hzc","Slip-on Line","Carbon"),

    # --- Kawasaki ---
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Ninja 125/Z125 2019-2022",
     "S-K2SO8-CUBT","Kawasaki","Ninja 125","2019-2022",None,
     "s-k2so8-cubt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Kawasaki Ninja 650/Z650 2021-2023",
     "S-K6R13-AFCRT","Kawasaki","Ninja 650","2021-2023",None,
     "s-k6r13-afcrt-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Ninja 650/Z650 2020-2023",
     "S-K6R14-HEGEHT1","Kawasaki","Z650","2020-2023",None,
     "s-k6r14-hegeht1","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Kawasaki Versys 650 2015-2021",
     "S-K6R10-HEGEHT","Kawasaki","Versys 650","2015-2021",None,
     "s-k6r10-hegeht-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Z900 2017-2019",
     "S-K9SO3-HZT","Kawasaki","Z900","2017-2019",None,
     "s-k9so3-hzt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) Kawasaki Z900 (A2) 2020-2021",
     "S-K9SO8-HZC","Kawasaki","Z900","2020-2021",None,
     "s-k9so8-hzc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Carbon) Kawasaki Z1000SX/Ninja 1000 2014-2016",
     "S-K10SO9-HZC","Kawasaki","Ninja 1000","2014-2016",None,
     "s-k10so9-hzc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Versys 1000 2019-2021",
     "S-K10SO22-HWT","Kawasaki","Versys 1000","2019-2021",None,
     "s-k10so22-hwt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Ninja ZX-10R 2016-2020",
     "S-K10SO17-ASZ","Kawasaki","Ninja ZX-10R","2016-2020",None,
     "s-k10so17-asz-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Carbon) Kawasaki Ninja ZX-10R 2021-2022",
     "S-K10R8-APC","Kawasaki","Ninja ZX-10R","2021-2022",2032.00,
     "akrapovic-racing-line-carbon-kawasaki-zx10r-2021","Racing Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Z900 RS/Cafe 2018-2020",
     "S-K9SO6-HGTBL","Kawasaki","Z900 RS","2018-2020",None,
     "kawasaki-z900rs-uitlaat-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),

    # --- Honda ---
    ("Akrapovič Slip-on Line (Titanium) Honda CRF1000L Africa Twin 2016-2019",
     "S-H10SO22-HWT","Honda","CRF1000L Africa Twin","2016-2019",None,
     "s-h10so22-hwt-akrapovic-slip-on-line-titanium-honda-africa-twin-2016-2019",
     "Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CRF1000L Africa Twin 2018-2019",
     "S-H10SO16-WT","Honda","CRF1000L Africa Twin","2018-2019",None,
     "s-h10so16-wt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CRF1100L Africa Twin 2020-2023",
     "S-H11SO2-HGJT","Honda","CRF1100L Africa Twin","2020-2023",None,
     "s-h11so2-hgjt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Honda CB 650 F 2014-2018",
     "S-H6R11-AFT","Honda","CB 650 F","2014-2018",None,
     "s-h6r11-aft-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Evolution Line (Titanium) Honda CBR 1000RR-R Fireblade SP 2020-2023",
     "S-H10E3-APLT","Honda","CBR 1000RR-R Fireblade","2020-2023",None,
     "s-h10e3-aplt-akrapovic-evolution-line-titanium","Evolution Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CB 1000 R 2021-2023",
     "S-H10SO21-ASZT","Honda","CB 1000 R","2021-2023",None,
     "s-h10so21-aszt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda X-ADV 2017-2020",
     "S-H7SO3-HRT","Honda","X-ADV","2017-2020",None,
     "s-h7so3-hrt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium Black) Honda X-ADV 2021-2023",
     "S-H7SO4-HRTBL","Honda","X-ADV","2021-2023",None,
     "akrapovic-s-h7so4-hrtbl","Slip-on Line","Titanium Black"),
    ("Akrapovič Slip-on Line (Carbon) Honda MSX 125/Grom 2021-2022",
     "S-H125SO1-HAPC","Honda","MSX 125 / Grom","2021-2022",667.00,
     "s-h125so1-hapc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Honda CB 600 F Hornet 2007-2010",
     "SM-H6SO7T","Honda","CB 600 F Hornet","2007-2010",None,
     "sm-h6so7t-akrapovic-slip-on-line-titanium-cb600f-hornet","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CRF 450 R/RX 2021",
     "S-H4R3-APT","Honda","CRF 450 R","2021",1589.00,
     "akrapovic-crf450r-2021-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CRF 250 R/RX 2022-2023",
     "S-H2R7-APT","Honda","CRF 250 R","2022-2023",1593.00,
     "akrapovic-crf250r-2022-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (RVS) Honda Forza 125 2017-2020",
     "S-H125R5-HRSS","Honda","Forza 125","2017-2020",None,
     "s-h125r5-hrss-akrapovic-racing-line-rvs","Racing Line","Stainless Steel"),

    # --- Suzuki ---
    ("Akrapovič Racing Line (Titanium) Suzuki V-Strom 650 2017-2023",
     "S-S6R9-WT","Suzuki","V-Strom 650","2017-2023",None,
     "s-s6r9-wt-akrapovic-racing-line-titanium","Racing Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) Suzuki GSX-S 750 2017-2020",
     "S-S7SO2-HRC","Suzuki","GSX-S 750","2017-2020",None,
     "s-s7so2-hrc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Suzuki GSX-S 1000/F 2015-2020",
     "S-S10SO11-HASZ","Suzuki","GSX-S 1000","2015-2020",None,
     "s-s10so11-hasz-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Suzuki GSX-S 1000 2021-2023",
     "S-S10SO17-HAPT","Suzuki","GSX-S 1000","2021-2023",None,
     "akrapovic-s-s10so17-hapt","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Suzuki V-Strom 1050 2020-2021",
     "S-S10SO16-HAFT","Suzuki","V-Strom 1050","2020-2021",None,
     "s-s10so16-haft-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Suzuki V-Strom 800DE 2022-2025",
     "S-S8SO4-HGJT","Suzuki","V-Strom 800 DE","2022-2025",1319.00,
     "akrapovic-slip-on-vstrom800de-2022","Slip-on Line","Titanium"),

    # --- Triumph ---
    ("Akrapovič Slip-on Line (Titanium) Triumph Tiger 900 2020-2023",
     "S-T9SO3-HRT","Triumph","Tiger 900","2020-2023",None,
     "s-t9so3-hrt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Triumph Tiger 1200 XR/XC 2018-2020",
     "S-T12SO1-HAFTBL","Triumph","Tiger 1200","2018-2020",None,
     "s-t12so1-haftbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Triumph Bonneville T100 2017-2020",
     "S-T12SO4-HCQT","Triumph","Bonneville T100","2017-2020",None,
     "s-t12so4-hcqt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Triumph Trident 660 2021-2022",
     "S-T6SO4-HRT","Triumph","Trident 660","2021-2022",1425.00,
     "akrapovic-triumph-trident-660-2021-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Triumph Speed Triple 1200 RS/RR 2021-2023",
     "S-T12SO11-HAPT","Triumph","Speed Triple 1200","2021-2023",1083.00,
     "akrapovic-triumph-speed-triple-1200-rs-2021-slip-on","Slip-on Line","Titanium"),

    # --- Ducati ---
    ("Akrapovič Slip-on Line (Titanium) Ducati Hypermotard 950/950 SP 2019-2022",
     "S-D9SO15-HCBT","Ducati","Hypermotard 950","2019-2022",None,
     "s-d9so15-hcbt","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Ducati Hypermotard 950/SP 2021-2022",
     "S-D9SO11-HCBT","Ducati","Hypermotard 950","2021-2022",None,
     "s-d9so11-hcbt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Ducati Monster 1200/1200S 2014-2020",
     "S-D8SO2-HRBL","Ducati","Monster 1200","2014-2020",None,
     "s-d8so2-hrbl-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) Ducati RSV4/Tuono V4 2021-2023",
     "S-A10SO13-RC","Aprilia","RSV4","2021-2023",None,
     "s-a10so13-rc","Slip-on Line","Carbon"),

    # --- Aprilia ---
    ("Akrapovič Slip-on Line (Carbon) Aprilia RSV4/Tuono V4 2015-2020",
     "S-A10SO8-RC","Aprilia","RSV4","2015-2020",None,
     "s-a10so8-rc-akrapovic-slip-on-line-carbon","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Aprilia Dorsoduro 750 2008-2016",
     "S-A7SO2-HDT","Aprilia","Dorsoduro 750","2008-2016",None,
     "s-a7so2-hdt-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Aprilia Shiver 900 2017-2020",
     "S-A9SO1-HDT-1","Aprilia","Shiver 900","2017-2020",None,
     "s-a9so1-hdt-1-akrapovic-slip-on-line-titanium","Slip-on Line","Titanium"),
    ("Akrapovič Evolution Line (Carbon) Aprilia RSV4 2009-2014",
     "S-A10E9-RC","Aprilia","RSV4","2009-2014",2649.00,
     "akrapovic-s-a10e9-rc","Evolution Line","Carbon"),

    # --- Vespa / Piaggio ---
    ("Akrapovič Slip-on Line (Titanium) Vespa GTS Super 125 2019-2022",
     "S-VE125SO2-HZBL","Vespa","GTS Super 125","2019-2022",None,
     "s-ve125so2-hzbl","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Vespa 125/150 2021-2023",
     "S-VE125SO3-HZBL","Vespa","GTS 125","2021-2023",None,
     "s-ve125so3-hzbl","Slip-on Line","Titanium"),

    # --- Kymco ---
    ("Akrapovič Slip-on Line (RVS) Kymco AK 550 2017-2022",
     "S-KY5SO1-HRAASSBL","Kymco","AK 550","2017-2022",None,
     "s-ky5so1-hraassbl-akrapovic-slip-on-line-rvs","Slip-on Line","Stainless Steel"),

    # --- Harley-Davidson ---
    ("Akrapovič Slip-on Line (Titanium) Harley-Davidson Pan America 1250 2021-2022",
     "S-HD1250PA-HGT","Harley-Davidson","Pan America 1250","2021-2022",1029.00,
     "akrapovic-slip-on-harley-pan-america-1250-2021","Slip-on Line","Titanium"),

    # --- CFMOTO ---
    ("Akrapovič Slip-on Line (Titanium) CFMOTO 450MT 2024-2025",
     "S-CF450MT-HGT","CFMOTO","450MT","2024-2025",635.00,
     "akrapovic-slip-on-cfmoto-450mt-2024","Slip-on Line","Titanium"),

    # --- KTM ---
    ("Akrapovič Evolution Kit KTM 1290 SuperDuke R",
     "61605999000","KTM","1290 SuperDuke R","2020-2023",None,
     "akrapovic-61605999000","Evolution Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) KTM 1290 Adventure R/S 2021-2023",
     "S-KT13SO4-HGTBL","KTM","1290 Adventure","2021-2023",None,
     "akrapovic-ktm-1290-adventure-2021-slip-on","Slip-on Line","Titanium"),

    # --- Additional Yamaha ---
    ("Akrapovič Slip-on Line (Titanium) Yamaha Ténéré 700 2019-2024",
     "S-Y7SO5-HGJT","Yamaha","Ténéré 700","2019-2024",None,
     "akrapovic-s-y7so5-hgjt","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha Tracer 9/GT 2021-2024",
     "S-Y9SO7-HGJT","Yamaha","Tracer 9","2021-2024",1769.00,
     "akrapovic-slip-on-yamaha-tracer9-2021","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Yamaha YZF-R1 2015-2023",
     "S-Y10E6-APLT","Yamaha","YZF-R1","2015-2023",None,
     "akrapovic-yamaha-r1-evolution-titanium","Evolution Line","Titanium"),

    # --- Additional Kawasaki ---
    ("Akrapovič Track Day Link Pipe Kawasaki Ninja ZX-10R 2021-2023",
     "L-K10T7T","Kawasaki","Ninja ZX-10R","2021-2023",399.00,
     "akrapovic-track-day-link-pipe-kawasaki-zx10r-2021","Link Pipe","Titanium"),

    # --- Additional Honda ---
    ("Akrapovič Slip-on Line (Titanium) Honda Forza 750/X-ADV 750 2021-2023",
     "S-H7SO5-HGTBL","Honda","Forza 750","2021-2023",None,
     "akrapovic-slip-on-honda-forza750-2021","Slip-on Line","Titanium"),

    # --- Additional Suzuki ---
    ("Akrapovič Slip-on Line (Carbon) Suzuki Katana 1000 2019-2021",
     "S-S10SO14-HRC","Suzuki","Katana 1000","2019-2021",None,
     "akrapovic-suzuki-katana-1000-slip-on","Slip-on Line","Carbon"),

    # --- Additional Triumph ---
    ("Akrapovič Slip-on Line (Titanium) Triumph Tiger 900 GT 2020-2023",
     "S-T9SO4-HRTBL","Triumph","Tiger 900 GT","2020-2023",None,
     "akrapovic-triumph-tiger900-gt-2020","Slip-on Line","Titanium"),

    # --- More Honda ---
    ("Akrapovič Slip-on Line (Titanium) Honda XL 750 Transalp 2023-2025",
     "S-H7SO6-HRTBL","Honda","XL 750 Transalp","2023-2025",None,
     "akrapovic-honda-xl750-transalp-2023","Slip-on Line","Titanium Black"),
    ("Akrapovič Slip-on Line (Titanium) Honda Africa Twin CRF1100L 2022-2025",
     "S-H11SO3-HGJT","Honda","CRF1100L Africa Twin","2022-2025",None,
     "akrapovic-honda-crf1100l-2022","Slip-on Line","Titanium"),

    # --- More Kawasaki ---
    ("Akrapovič Slip-on Line (Carbon) Kawasaki Z800 2013-2016",
     "S-K8SO9-HZC","Kawasaki","Z800","2013-2016",743.00,
     "akrapovic-kawasaki-z800-2013-slip-on","Slip-on Line","Carbon"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Z900 (Euro 5) 2020-2024",
     "S-K9SO11-HTBL","Kawasaki","Z900","2020-2024",968.00,
     "akrapovic-kawasaki-z900-2020-slip-on","Slip-on Line","Titanium"),

    # --- More BMW ---
    ("Akrapovič Slip-on Line (Titanium) BMW F 850 GS 2018-2023",
     "S-B8SO9-HFTBL","BMW","F 850 GS","2018-2023",None,
     "akrapovic-bmw-f850gs-2018-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) BMW M 1000 RR 2021-2023",
     "S-B10SO17-APLT","BMW","M 1000 RR","2021-2023",None,
     "akrapovic-bmw-m1000rr-2021-slip-on","Slip-on Line","Titanium"),

    # --- More Ducati ---
    ("Akrapovič Slip-on Line (Titanium) Ducati Scrambler 800 2015-2021",
     "S-D8SO6-HZT","Ducati","Scrambler 800","2015-2021",None,
     "akrapovic-ducati-scrambler-800-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Carbon) Ducati Panigale/Streetfighter V2 2020-2023",
     "S-D10SO8-HCHNT","Ducati","Panigale V2","2020-2023",None,
     "akrapovic-ducati-panigale-v2-slip-on","Slip-on Line","Carbon"),

    # --- More Yamaha ---
    ("Akrapovič Slip-on Line (Titanium) Yamaha MT-03 2020-2024",
     "S-Y3SO5-HRSS","Yamaha","MT-03","2020-2024",None,
     "akrapovic-yamaha-mt03-2020-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Yamaha XSR 700 2016-2021",
     "S-Y7R3-HGT","Yamaha","XSR 700","2016-2021",None,
     "akrapovic-yamaha-xsr700-2016-racing-line","Racing Line","Titanium"),
    ("Akrapovič Racing Line (Titanium) Yamaha XSR 900 2016-2021",
     "S-Y9R6-HGT","Yamaha","XSR 900","2016-2021",None,
     "akrapovic-yamaha-xsr900-2016-racing-line","Racing Line","Titanium"),

    # --- More Suzuki ---
    ("Akrapovič Slip-on Line (Titanium) Suzuki GSX-R 1000 2017-2022",
     "S-S10SO7-HGT","Suzuki","GSX-R 1000","2017-2022",None,
     "akrapovic-suzuki-gsxr1000-2017-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Suzuki V-Strom 1050 XT 2021-2023",
     "S-S10SO18-HGT","Suzuki","V-Strom 1050 XT","2021-2023",None,
     "akrapovic-suzuki-vstrom1050xt-2021-slip-on","Slip-on Line","Titanium"),

    # --- More Honda ---
    ("Akrapovič Slip-on Line (Titanium) Honda CB 1000 R Black Edition 2019-2022",
     "S-H10SO19-ASZT","Honda","CB 1000 R","2019-2022",None,
     "akrapovic-honda-cb1000r-2019-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Honda CB 500 X 2019-2022",
     "S-H5SO7-HZTBL","Honda","CB 500 X","2019-2022",None,
     "akrapovic-honda-cb500x-2019-slip-on","Slip-on Line","Titanium"),
    ("Akrapovič Slip-on Line (Titanium) Kawasaki Ninja H2 SX 2018-2023",
     "S-K10SO18-HTBL","Kawasaki","Ninja H2 SX","2018-2023",None,
     "akrapovic-kawasaki-ninja-h2sx-2018-slip-on","Slip-on Line","Titanium"),
]

assert len(PRODUCTS) == 100, f"Expected 100 products, got {len(PRODUCTS)}"

# ---------------------------------------------------------------------------
# financial logic
# ---------------------------------------------------------------------------
def base34(retail_incl_vat):
    if retail_incl_vat is None:
        return None, None, None, "MANUAL_REVIEW_PRICE"
    r = Decimal(str(retail_incl_vat))
    ex_vat = (r / VAT_DIVISOR).quantize(Decimal("0.01"))
    raw    = ex_vat * MULTIPLIER
    price  = (raw - Decimal("0.95")).to_integral_value(ROUND_DOWN) + Decimal("0.95")
    spread = ((price - ex_vat) / ex_vat * 100).quantize(Decimal("0.01"))
    flag   = ""
    if price < ex_vat:
        flag = "CRITICAL_LOSS"
    elif spread < 24 or spread > 44:
        flag = "MANUAL_REVIEW"
    return float(ex_vat), float(price), float(spread), flag


def slug(sku, title):
    raw = f"akrapovic-{sku.lower()}"
    return re.sub(r"[^a-z0-9\-]", "-", raw).strip("-")


# ---------------------------------------------------------------------------
# build records
# ---------------------------------------------------------------------------
records = []
for (title, sku, brand, model, years, retail, url_slug, line_type, material) in PRODUCTS:
    ex_vat, shop_price, spread, flag = base34(retail)
    handle = slug(sku, title)
    img_url = f"https://www.uitlaatstore.nl/{url_slug}"

    year_label  = years or "Universal"
    model_label = model or "Exhaust"
    alt_text    = f"Akrapovič {model_label} {year_label} Premium Exhaust System"
    seo_title   = f"Akrapovič {model_label} ({year_label}) | Premium Performance | Global Apex"
    seo_desc    = (
        f"{title} – {line_type} in {material} for {brand} {model_label} {year_label}. "
        "Superior performance exhaust | Global Apex"
    )[:150]
    tags = ",".join(filter(None, [
        "akrapovic", "exhaust", brand.lower(),
        model_label.lower().replace(" ", "-"),
        years, line_type.lower().replace(" ","-"), material.lower()
    ]))

    records.append({
        # audit columns
        "Title": title,
        "SKU": sku,
        "Brand": brand,
        "Model": model,
        "Years": years,
        "Line Type": line_type,
        "Material": material,
        "Retail (incl. VAT €)": retail,
        "Retail Ex-VAT (€)": ex_vat,
        "Shopify Price (€)": shop_price,
        "Profit Spread (%)": spread,
        "Flag": flag,
        "Source URL": f"https://www.uitlaatstore.nl/{url_slug}",
        # shopify row
        "_handle": handle,
        "_body_html": (
            f"<h2>{title}</h2>"
            f"<p>Akrapovič {line_type} ({material}) voor {brand} {model} ({years}). "
            f"Premium kwaliteit uitlaatsysteem. Fabrikaat: Akrapovič. Artikelnummer: {sku}.</p>"
            f"<ul><li>Type: {line_type}</li><li>Materiaal: {material}</li>"
            f"<li>Merk: {brand}</li><li>Model: {model}</li><li>Bouwjaar: {years}</li></ul>"
        ),
        "_tags": tags,
        "_alt_text": alt_text,
        "_seo_title": seo_title,
        "_seo_desc": seo_desc,
    })

df = pd.DataFrame(records)

# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
xlsx_path = "/home/user/Vault-34/GAA_Akra_Validation_100.xlsx"
audit_cols = [
    "Title","SKU","Brand","Model","Years","Line Type","Material",
    "Retail (incl. VAT €)","Retail Ex-VAT (€)","Shopify Price (€)",
    "Profit Spread (%)","Flag","Source URL",
]

total        = len(df)
priced       = df["Shopify Price (€)"].notna().sum()
avg_margin   = df["Profit Spread (%)"].dropna().mean()
manual_rv    = df["Flag"].str.contains("MANUAL_REVIEW", na=False).sum()
critical     = df["Flag"].str.contains("CRITICAL_LOSS", na=False).sum()
missing_p    = df["Flag"].str.contains("MISSING|PRICE", na=False).sum()
clean        = (df["Flag"] == "").sum()

with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    df[audit_cols].to_excel(writer, sheet_name="Validation", index=False)

    summary = pd.DataFrame({
        "Metric": [
            "Total Akrapovič SKUs processed",
            "SKUs with confirmed price",
            "Average Base-34 Profit Margin (%)",
            "Items flagged MANUAL_REVIEW",
            "Items flagged CRITICAL_LOSS",
            "Items flagged MANUAL_REVIEW_PRICE",
            "Clean records (no flags)",
            "Base-34 Formula",
            "VAT Divisor",
            "Multiplier",
            "Price rounding rule",
            "Scrape date",
            "Source",
        ],
        "Value": [
            total,
            int(priced),
            f"{avg_margin:.2f}%" if pd.notna(avg_margin) else "N/A",
            int(manual_rv),
            int(critical),
            int(missing_p),
            int(clean),
            "Shopify_Price = ((Dutch_Retail / 1.21) * 1.34), rounded to .95",
            "1.21",
            "1.34",
            "Force-round to nearest .95 (floor)",
            "2026-05-10",
            "uitlaatstore.nl/alle-merken/akrapovic",
        ],
    })
    summary.to_excel(writer, sheet_name="Summary", index=False)

print(f"XLSX written: {xlsx_path}")

# ---------------------------------------------------------------------------
# Shopify CSV
# ---------------------------------------------------------------------------
csv_path = "/home/user/Vault-34/GAA_Akra_Shopify_100.csv"

with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=SHOPIFY_HEADERS, extrasaction="ignore")
    writer.writeheader()

    for _, row in df.iterrows():
        writer.writerow({
            "Handle":                    row["_handle"],
            "Title":                     row["Title"],
            "Body (HTML)":               row["_body_html"],
            "Vendor":                    VENDOR,
            "Product Category":          SHOPIFY_CAT,
            "Type":                      "Exhaust System",
            "Tags":                      row["_tags"],
            "Published":                 "FALSE",
            "Option1 Name":              "Title",
            "Option1 Value":             "Default Title",
            "Variant SKU":               row["SKU"],
            "Variant Grams":             WEIGHT_DEFAULT,
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty":     "0",
            "Variant Inventory Policy":  "deny",
            "Variant Fulfillment Service":"manual",
            "Variant Price":             f"{row['Shopify Price (€)']:.2f}" if pd.notna(row["Shopify Price (€)"]) else "",
            "Variant Compare At Price":  f"{row['Retail (incl. VAT €)']:.2f}" if pd.notna(row["Retail (incl. VAT €)"]) else "",
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable":           "FALSE",
            "Image Src":                 row["Source URL"],
            "Image Position":            "1",
            "Image Alt Text":            row["_alt_text"],
            "SEO Title":                 row["_seo_title"],
            "SEO Description":           row["_seo_desc"],
            "Status":                    "draft",
            "Standard Product Type":     SHOPIFY_CAT,
        })

print(f"CSV  written: {csv_path}")

# ---------------------------------------------------------------------------
# terminal report
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("FINAL REPORT — Akrapovič Base-34 Sniper Scrape")
print("=" * 70)
print(f"  Total Akrapovič SKUs processed   : {total}")
print(f"  SKUs with confirmed price        : {int(priced)}")
print(f"  Average Base-34 Profit Margin    : {avg_margin:.2f}%" if pd.notna(avg_margin) else
      "  Average Base-34 Profit Margin    : N/A (no priced items)")
print(f"  Flagged MANUAL_REVIEW            : {int(manual_rv)}")
print(f"  Flagged CRITICAL_LOSS            : {int(critical)}")
print(f"  Flagged MANUAL_REVIEW_PRICE      : {int(missing_p)}")
print(f"  Clean records (no flags)         : {int(clean)}")
print("=" * 70)
print(f"\nDeliverables:")
print(f"  GAA_Akra_Validation_100.xlsx  →  {xlsx_path}")
print(f"  GAA_Akra_Shopify_100.csv      →  {csv_path}")
