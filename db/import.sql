BEGIN TRANSACTION;
CREATE TABLE accounts (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    kind  TEXT NOT NULL CHECK (kind IN ('bank', 'credit_card'))
);
INSERT INTO "accounts" VALUES(1,'Bankkonto','bank');
INSERT INTO "accounts" VALUES(2,'Kredittkort','credit_card');
CREATE TABLE categories (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    kind   TEXT NOT NULL CHECK (kind IN ('expense', 'income', 'transfer')),
    parent TEXT
);
INSERT INTO "categories" VALUES(1,'Salary','income',NULL);
INSERT INTO "categories" VALUES(2,'Employer reimbursement','income',NULL);
INSERT INTO "categories" VALUES(3,'Internal transfer','transfer',NULL);
INSERT INTO "categories" VALUES(4,'Credit card payment','transfer',NULL);
INSERT INTO "categories" VALUES(5,'Groceries','expense',NULL);
INSERT INTO "categories" VALUES(6,'Convenience & kiosk','expense',NULL);
INSERT INTO "categories" VALUES(7,'Cafe & bakery','expense',NULL);
INSERT INTO "categories" VALUES(8,'Restaurants & takeaway','expense',NULL);
INSERT INTO "categories" VALUES(9,'Bars & nightlife','expense',NULL);
INSERT INTO "categories" VALUES(10,'Public transport','expense',NULL);
INSERT INTO "categories" VALUES(11,'Taxi & ride-hailing','expense',NULL);
INSERT INTO "categories" VALUES(12,'Fuel & EV charging','expense',NULL);
INSERT INTO "categories" VALUES(13,'Clothing & shoes','expense',NULL);
INSERT INTO "categories" VALUES(14,'Sports & outdoor','expense',NULL);
INSERT INTO "categories" VALUES(15,'Home & furniture','expense',NULL);
INSERT INTO "categories" VALUES(16,'Flowers & plants','expense',NULL);
INSERT INTO "categories" VALUES(17,'Personal care','expense',NULL);
INSERT INTO "categories" VALUES(18,'Health - dental','expense',NULL);
INSERT INTO "categories" VALUES(19,'Health - pharmacy','expense',NULL);
INSERT INTO "categories" VALUES(20,'Health - doctor','expense',NULL);
INSERT INTO "categories" VALUES(21,'Utilities - electricity','expense',NULL);
INSERT INTO "categories" VALUES(22,'Insurance','expense',NULL);
INSERT INTO "categories" VALUES(23,'Gym & fitness','expense',NULL);
INSERT INTO "categories" VALUES(24,'Subscriptions','expense',NULL);
INSERT INTO "categories" VALUES(25,'Memberships','expense',NULL);
INSERT INTO "categories" VALUES(26,'Entertainment','expense',NULL);
INSERT INTO "categories" VALUES(27,'Accommodation','expense',NULL);
INSERT INTO "categories" VALUES(28,'Books','expense',NULL);
INSERT INTO "categories" VALUES(29,'Gifts','expense',NULL);
INSERT INTO "categories" VALUES(30,'Mortgage & loan','expense',NULL);
INSERT INTO "categories" VALUES(31,'Student loan','expense',NULL);
INSERT INTO "categories" VALUES(32,'Mortgage - interest','expense',NULL);
INSERT INTO "categories" VALUES(33,'Mortgage - fees','expense',NULL);
INSERT INTO "categories" VALUES(34,'Mortgage - principal','transfer',NULL);
INSERT INTO "categories" VALUES(35,'Employer loan repayment','transfer',NULL);
INSERT INTO "categories" VALUES(36,'Vipps P2P - unspecified','expense',NULL);
INSERT INTO "categories" VALUES(37,'Uncategorised','expense',NULL);
CREATE TABLE import_batches (
    id           INTEGER PRIMARY KEY,
    source_file  TEXT NOT NULL,
    row_count    INTEGER NOT NULL,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    imported_at  TEXT NOT NULL
);
INSERT INTO "import_batches" VALUES(1,'Kontoutskrift.xlsx',123,0,'2026-08-22T17:04:46');
INSERT INTO "import_batches" VALUES(2,'transaksjonsliste(1).xlsx',44,1,'2026-08-22T17:04:46');
INSERT INTO "import_batches" VALUES(3,'transaksjonsliste.xlsx',14,1,'2026-08-22T17:04:46');
CREATE TABLE transactions (
    id           INTEGER PRIMARY KEY,
    date         TEXT    NOT NULL,              -- ISO yyyy-mm-dd
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    description  TEXT    NOT NULL,              -- verbatim from statement
    amount       REAL    NOT NULL,              -- signed, NOK
    category_id  INTEGER REFERENCES categories(id),
    is_transfer  INTEGER NOT NULL DEFAULT 0 CHECK (is_transfer IN (0, 1)),
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    counterparty TEXT,                           -- Vipps P2P name, when detected
    memo         TEXT,                           -- Vipps memo that drove the category
    note         TEXT,
    batch_id     INTEGER NOT NULL REFERENCES import_batches(id),
    source_row   INTEGER NOT NULL,              -- 1-based row in the source sheet
    is_derived   INTEGER NOT NULL DEFAULT 0 CHECK (is_derived IN (0, 1)),
    -- Same merchant, same day, same amount happens for real (two coffees paid
    -- separately), so the source row number is part of the identity. One source
    -- row can also expand into several derived rows (a loan term split into
    -- interest / principal / fee), hence description+amount in the key too.
    UNIQUE (batch_id, source_row, description, amount)
);
INSERT INTO "transactions" VALUES(1,'2026-06-30',1,'Overføring  90200000000 Ingvild Kvamme Berg Tpp: Vipps',190.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,2,0);
INSERT INTO "transactions" VALUES(2,'2026-07-01',1,'Overføring  90300000000 Ingvild Kvamme Berg Tpp: Vipps',102.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,3,0);
INSERT INTO "transactions" VALUES(3,'2026-07-01',1,'Overføring  9040000000 Sindre Aalborg LatteTpp: Vipps Mobilepay AS',-69.0,7,0,0,'Sindre Aalborg LatteTpp',NULL,NULL,1,4,0);
INSERT INTO "transactions" VALUES(4,'2026-07-01',1,'Overføring  9050000000 Solveig Marte Vangen HumoretatenTpp: Vipps Mobilepay AS',-140.0,26,0,0,'Solveig Marte Vangen HumoretatenTpp',NULL,NULL,1,5,0);
INSERT INTO "transactions" VALUES(5,'2026-07-01',1,'Kontoregulering  237 Ukespenger',2200.0,3,1,0,NULL,NULL,NULL,1,6,0);
INSERT INTO "transactions" VALUES(6,'2026-07-01',1,'Varekjøp Deli De Luca Os Jernbanetorg Oslo Dato 01.07 kl. 14.53',-131.9,6,0,0,NULL,NULL,NULL,1,7,0);
INSERT INTO "transactions" VALUES(7,'2026-07-01',1,'Varekjøp Narvesen 417 In Jernbanetorg Oslo Dato 01.07 kl. 13.10',-40.9,6,0,0,NULL,NULL,NULL,1,8,0);
INSERT INTO "transactions" VALUES(8,'2026-07-01',1,'Varekjøp Tog Ga (a349) Tøyenbekken 0188 Osl Dato 01.07 kl. 17.32',-48.0,10,0,0,NULL,NULL,NULL,1,9,0);
INSERT INTO "transactions" VALUES(9,'2026-07-02',1,'Overføring Bente Kathrine Berntzen MatRef:',700.0,5,0,0,NULL,NULL,NULL,1,10,0);
INSERT INTO "transactions" VALUES(10,'2026-07-02',1,'Varekjøp Extra Drangedal Lauvåsen 1 Drangeda Dato 02.07 kl. 15.47',-700.8,5,0,0,NULL,NULL,NULL,1,11,0);
INSERT INTO "transactions" VALUES(11,'2026-07-02',1,'Visa  100021  Www Coop No Medlem',-300.0,25,0,0,'Www Coop No Medlem',NULL,NULL,1,12,0);
INSERT INTO "transactions" VALUES(12,'2026-07-05',1,'Overføring  90700000000 Ingvild Kvamme Berg Tpp: Vipps',106.5,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,13,0);
INSERT INTO "transactions" VALUES(13,'2026-07-05',1,'Overføring  90800000000 Ingvild Kvamme Berg Tpp: Vipps',180.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,14,0);
INSERT INTO "transactions" VALUES(14,'2026-07-04',1,'Overføring Innland  1362 Tor Bolle Waage Stavær',300.0,36,0,1,NULL,NULL,NULL,1,15,0);
INSERT INTO "transactions" VALUES(15,'2026-07-05',1,'Varekjøp Narvesen 885 Ri Thorvald Mey Oslo Dato 05.07 kl. 14.15',-32.0,6,0,0,NULL,NULL,NULL,1,16,0);
INSERT INTO "transactions" VALUES(16,'2026-07-05',1,'Varekjøp Grød Markveien Markveien 67 Oslo Dato 05.07 kl. 12.34',-213.0,7,0,0,NULL,NULL,NULL,1,17,0);
INSERT INTO "transactions" VALUES(17,'2026-07-04',1,'Varekjøp Circle k Telema Prestmoen 4 Porsgr Dato 04.07 kl. 10.36',-35.9,7,0,0,NULL,NULL,NULL,1,18,0);
INSERT INTO "transactions" VALUES(18,'2026-07-04',1,'Varekjøp Vitusapotek Sto Vitaminvn. 7 Oslo Dato 04.07 kl. 15.10',-99.9,19,0,0,NULL,NULL,NULL,1,19,0);
INSERT INTO "transactions" VALUES(19,'2026-07-04',1,'Visa  100021  Vipps:sindre Aalborg',-30.0,36,0,1,'sindre Aalborg',NULL,NULL,1,20,0);
INSERT INTO "transactions" VALUES(20,'2026-07-08',1,'Kontoregulering  239 Ukespenger',1800.0,3,1,0,NULL,NULL,NULL,1,21,0);
INSERT INTO "transactions" VALUES(21,'2026-07-07',1,'Varekjøp Leirvassbu Turi Strandvegen Lesjas Dato 07.07 kl. 17.20',-50.0,27,0,0,NULL,NULL,NULL,1,22,0);
INSERT INTO "transactions" VALUES(22,'2026-07-10',1,'Varekjøp Gjendebu. Vagstadbygge Innvik Dato 10.07 kl. 12.40',-95.0,27,0,0,NULL,NULL,NULL,1,23,0);
INSERT INTO "transactions" VALUES(23,'2026-07-10',1,'Varekjøp Gjendebu. Vagstadbygge Innvik Dato 10.07 kl. 13.54',-120.0,27,0,0,NULL,NULL,NULL,1,24,0);
INSERT INTO "transactions" VALUES(24,'2026-07-10',1,'Varekjøp Gjendebu. Vagstadbygge Innvik Dato 10.07 kl. 14.52',-50.0,27,0,0,NULL,NULL,NULL,1,25,0);
INSERT INTO "transactions" VALUES(25,'2026-07-13',1,'Giro  391 Fjordkraft AS AvtalegiroFjordkraft AS',-397.11,21,0,0,NULL,NULL,NULL,1,26,0);
INSERT INTO "transactions" VALUES(26,'2026-07-11',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 11.07 kl. 14.43',-81.8,5,0,0,NULL,NULL,NULL,1,27,0);
INSERT INTO "transactions" VALUES(27,'2026-07-11',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 11.07 kl. 09.31',-380.68,5,0,0,NULL,NULL,NULL,1,28,0);
INSERT INTO "transactions" VALUES(28,'2026-07-12',1,'Varekjøp Joker Løren Sta Peter Møller Oslo Dato 12.07 kl. 15.51',-124.13,5,0,0,NULL,NULL,NULL,1,29,0);
INSERT INTO "transactions" VALUES(29,'2026-07-11',1,'Varekjøp Sats Hasle Grenseveien Oslo Dato 11.07 kl. 14.27',-69.0,23,0,0,NULL,NULL,NULL,1,30,0);
INSERT INTO "transactions" VALUES(30,'2026-07-11',1,'Varekjøp Kb37 Løren Lørenveien 4 Oslo Dato 11.07 kl. 09.42',-66.0,7,0,0,NULL,NULL,NULL,1,31,0);
INSERT INTO "transactions" VALUES(31,'2026-07-11',1,'Varekjøp Meny Løren (gln Lørenveien 4 Oslo Dato 11.07 kl. 17.39',-63.21,5,0,0,NULL,NULL,NULL,1,32,0);
INSERT INTO "transactions" VALUES(32,'2026-07-12',1,'Varekjøp Avd.47 Baker No Børsteveien Oslo Dato 12.07 kl. 11.18',-54.0,7,0,0,NULL,NULL,NULL,1,33,0);
INSERT INTO "transactions" VALUES(33,'2026-07-10',1,'Varekjøp Rema Leira Skulevegen 7 Leira i Val Dato 10.07 kl. 19.49',-74.9,5,0,0,NULL,NULL,NULL,1,34,0);
INSERT INTO "transactions" VALUES(34,'2026-07-10',1,'Varekjøp Burger King Lei Markavegen Leira i Dato 10.07 kl. 19.06',-228.0,8,0,0,NULL,NULL,NULL,1,35,0);
INSERT INTO "transactions" VALUES(35,'2026-07-13',1,'Varekjøp Kb37 Løren Lørenveien 4 Oslo Dato 13.07 kl. 07.16',-44.0,7,0,0,NULL,NULL,NULL,1,36,0);
INSERT INTO "transactions" VALUES(36,'2026-07-10',1,'Visa  100021  Uno-x 72024 Leira El',-233.56,12,0,0,NULL,NULL,NULL,1,37,0);
INSERT INTO "transactions" VALUES(37,'2026-07-11',1,'Visa  100121  Vipps:sindre Aalborg',-160.0,36,0,1,'sindre Aalborg',NULL,NULL,1,38,0);
INSERT INTO "transactions" VALUES(38,'2026-07-11',1,'Visa  100221  Vipps:tor Bolle Waage',-892.95,36,0,1,'tor Bolle Waage',NULL,NULL,1,39,0);
INSERT INTO "transactions" VALUES(39,'2026-07-12',1,'Visa  100321  Baneleie - Squash',-299.0,14,0,0,NULL,NULL,NULL,1,40,0);
INSERT INTO "transactions" VALUES(40,'2026-07-13',1,'Varekjøp Rema 1000 Sinse Sinsenveien Oslo Dato 13.07 kl. 17.30',-70.4,5,0,0,NULL,NULL,NULL,1,41,0);
INSERT INTO "transactions" VALUES(41,'2026-07-14',1,'Varekjøp Rema 1000 Sinse Sinsenveien Oslo Dato 14.07 kl. 08.18',-69.8,5,0,0,NULL,NULL,NULL,1,42,0);
INSERT INTO "transactions" VALUES(42,'2026-07-14',1,'Overføring  91200000000 Ingvild Kvamme Berg Tpp: Vipps',159.5,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,43,0);
INSERT INTO "transactions" VALUES(43,'2026-07-15',1,'Kontoregulering  242 Ukespenger',2200.0,3,1,0,NULL,NULL,NULL,1,44,0);
INSERT INTO "transactions" VALUES(44,'2026-07-14',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 14.07 kl. 18.49',-87.9,5,0,0,NULL,NULL,NULL,1,45,0);
INSERT INTO "transactions" VALUES(45,'2026-07-15',1,'Overføring Innland  91300000000 Torkel Aalborg',44.0,36,0,1,'Torkel Aalborg',NULL,NULL,1,46,0);
INSERT INTO "transactions" VALUES(46,'2026-07-15',1,'Varekjøp Kiwi 373 Solli Henrik Ibsen Oslo Dato 15.07 kl. 13.57',-142.8,5,0,0,NULL,NULL,NULL,1,47,0);
INSERT INTO "transactions" VALUES(47,'2026-07-14',1,'Visa  100021  Dominos',-319.0,8,0,0,NULL,NULL,NULL,1,48,0);
INSERT INTO "transactions" VALUES(48,'2026-07-15',1,'Varekjøp Rema 1000 Sinse Sinsenveien Oslo Dato 15.07 kl. 17.59',-89.8,5,0,0,NULL,NULL,NULL,1,49,0);
INSERT INTO "transactions" VALUES(49,'2026-07-16',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 16.07 kl. 12.26',-193.19,5,0,0,NULL,NULL,NULL,1,50,0);
INSERT INTO "transactions" VALUES(50,'2026-07-17',1,'Overføring Sindre Aalborg Stol Fra JyskRef:',1800.0,15,0,0,NULL,NULL,NULL,1,51,0);
INSERT INTO "transactions" VALUES(51,'2026-07-16',1,'Visa  100022  Nok 219,00 Spotifyse',-219.0,24,0,0,NULL,NULL,NULL,1,52,0);
INSERT INTO "transactions" VALUES(52,'2026-07-17',1,'Lønn  900112233 Nordvest Teknikk AS',41113.67,1,0,0,'Nordvest Teknikk AS',NULL,NULL,1,53,0);
INSERT INTO "transactions" VALUES(53,'2026-07-18',1,'Overføring  91500000000 Ingvild Kvamme Berg Tpp: Vipps',150.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,54,0);
INSERT INTO "transactions" VALUES(54,'2026-07-20',1,'Overføring  91600000000 Ingvild Kvamme Berg Tpp: Vipps',78.5,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,55,0);
INSERT INTO "transactions" VALUES(55,'2026-07-20',1,'Giro  394 Sats Vest AS AvtalegiroSats Vest AS',-394.0,23,0,0,NULL,NULL,NULL,1,56,0);
INSERT INTO "transactions" VALUES(56,'2026-07-20',1,'Giro  393 Gjensidige Forsikring Asa AvtalegiroGjensidige Forsikring Asa',-69.0,22,0,0,NULL,NULL,NULL,1,57,0);
INSERT INTO "transactions" VALUES(57,'2026-07-20',1,'Kontoregulering  382 Overføring Mellom Egne Konti',-2000.0,3,1,0,NULL,NULL,NULL,1,58,0);
INSERT INTO "transactions" VALUES(58,'2026-07-17',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 17.07 kl. 17.14',-161.14,5,0,0,NULL,NULL,NULL,1,59,0);
INSERT INTO "transactions" VALUES(59,'2026-07-18',1,'Varekjøp Avd.47 Baker No Børsteveien Oslo Dato 18.07 kl. 13.28',-300.0,7,0,0,NULL,NULL,NULL,1,60,0);
INSERT INTO "transactions" VALUES(60,'2026-07-18',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 18.07 kl. 13.42',-37.9,5,0,0,NULL,NULL,NULL,1,61,0);
INSERT INTO "transactions" VALUES(61,'2026-07-17',1,'Varekjøp Haugen Ullevålsveie Oslo Dato 17.07 kl. 18.48',-58.0,9,0,0,NULL,NULL,NULL,1,62,0);
INSERT INTO "transactions" VALUES(62,'2026-07-17',1,'Varekjøp Haugen Ullevålsveie Oslo Dato 17.07 kl. 19.34',-114.0,9,0,0,NULL,NULL,NULL,1,63,0);
INSERT INTO "transactions" VALUES(63,'2026-07-18',1,'Varekjøp Rema Majorstua Sørkedalsvei Oslo Dato 18.07 kl. 20.46',-40.9,5,0,0,NULL,NULL,NULL,1,64,0);
INSERT INTO "transactions" VALUES(64,'2026-07-18',1,'Varekjøp Jysk N603 Hasle Bøkkeveien 4 Oslo Dato 18.07 kl. 11.17',-1800.0,15,0,0,NULL,NULL,NULL,1,65,0);
INSERT INTO "transactions" VALUES(65,'2026-07-18',1,'Varekjøp Meny Løren (gln Lørenveien 4 Oslo Dato 18.07 kl. 13.17',-168.52,5,0,0,NULL,NULL,NULL,1,66,0);
INSERT INTO "transactions" VALUES(66,'2026-07-20',1,'Overføring Innland  9170000000 Spotify Sindre Aalborg',44.0,24,0,0,'Spotify Sindre Aalborg',NULL,NULL,1,67,0);
INSERT INTO "transactions" VALUES(67,'2026-07-20',1,'Varekjøp Avd.47 Baker No Børsteveien Oslo Dato 20.07 kl. 14.48',-157.0,7,0,0,NULL,NULL,NULL,1,68,0);
INSERT INTO "transactions" VALUES(69,'2026-07-18',1,'Visa  100021  Vipps:torkel Aalborg',-265.0,36,0,1,'torkel Aalborg',NULL,NULL,1,70,0);
INSERT INTO "transactions" VALUES(70,'2026-07-18',1,'Visa  100121  Hasle Torg',-50.0,5,0,0,'Hasle Torg',NULL,NULL,1,71,0);
INSERT INTO "transactions" VALUES(71,'2026-07-20',1,'Kontoregulering  397 Mobil Overføring',-1700.0,3,1,0,NULL,NULL,NULL,1,72,0);
INSERT INTO "transactions" VALUES(72,'2026-07-20',1,'Kontoregulering  398 Mobil Overføring',-16000.0,3,1,0,NULL,NULL,NULL,1,73,0);
INSERT INTO "transactions" VALUES(73,'2026-07-20',1,'Overføring Innland  396 Til : 99900011122 Mobil Betaling',-4982.8,4,1,0,'Mobil Betaling',NULL,NULL,1,74,0);
INSERT INTO "transactions" VALUES(74,'2026-07-20',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 20.07 kl. 19.04',-223.2,5,0,0,NULL,NULL,NULL,1,75,0);
INSERT INTO "transactions" VALUES(75,'2026-07-21',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 21.07 kl. 14.15',-55.1,5,0,0,NULL,NULL,NULL,1,76,0);
INSERT INTO "transactions" VALUES(76,'2026-07-22',1,'Overføring  91800000000 Ingvild Kvamme Berg Tpp: Vipps',260.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,77,0);
INSERT INTO "transactions" VALUES(77,'2026-07-22',1,'Kontoregulering  243 Ukespenger',2200.0,3,1,0,NULL,NULL,NULL,1,78,0);
INSERT INTO "transactions" VALUES(78,'2026-07-21',1,'Varekjøp Blomsterpikenes Lørenveien 4 Oslo Dato 21.07 kl. 15.53',-100.0,16,0,0,NULL,NULL,NULL,1,79,0);
INSERT INTO "transactions" VALUES(79,'2026-07-21',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 21.07 kl. 16.45',-119.6,5,0,0,NULL,NULL,NULL,1,80,0);
INSERT INTO "transactions" VALUES(80,'2026-07-21',1,'Varekjøp Dios House Of b Ulvenveien 7 Oslo Dato 21.07 kl. 15.27',-600.0,13,0,0,NULL,NULL,NULL,1,81,0);
INSERT INTO "transactions" VALUES(81,'2026-07-21',1,'Varekjøp Normal Oslo Vin Bøkkerveien Oslo Dato 21.07 kl. 15.46',-56.0,17,0,0,NULL,NULL,NULL,1,82,0);
INSERT INTO "transactions" VALUES(82,'2026-07-22',1,'Varekjøp Meny Telemarksp Prestemoen 6 Eidang Dato 22.07 kl. 14.28',-504.28,5,0,0,NULL,NULL,NULL,1,83,0);
INSERT INTO "transactions" VALUES(83,'2026-07-21',1,'Visa  100021  Vipps:torkel Aalborg',-210.0,36,0,1,'torkel Aalborg',NULL,NULL,1,84,0);
INSERT INTO "transactions" VALUES(84,'2026-07-24',1,'Giro  921000000 Nordvest Teknikk AS',835.8,2,0,1,'Nordvest Teknikk AS',NULL,NULL,1,85,0);
INSERT INTO "transactions" VALUES(85,'2026-07-23',1,'Overføring  91900000000 Ingvild Kvamme Berg IsTpp: Vipps',25.0,7,0,0,'Ingvild Kvamme Berg IsTpp',NULL,NULL,1,86,0);
INSERT INTO "transactions" VALUES(86,'2026-07-23',1,'Overføring  92000000000 Ingvild Kvamme Berg Tpp: Vipps',130.0,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,87,0);
INSERT INTO "transactions" VALUES(87,'2026-07-24',1,'Overføring  92200000000 Ingvild Kvamme Berg LadingTpp: Vipps',140.0,12,0,0,'Ingvild Kvamme Berg LadingTpp',NULL,NULL,1,88,0);
INSERT INTO "transactions" VALUES(88,'2026-07-23',1,'Varekjøp Spar Drangedal Kåsmyra 3750 Dr.dal Dato 23.07 kl. 16.45',-258.5,5,0,0,NULL,NULL,NULL,1,89,0);
INSERT INTO "transactions" VALUES(89,'2026-07-24',1,'Varekjøp Mcd 082 Fokserødveie Sandefjord Dato 24.07 kl. 12.20',-42.0,8,0,0,NULL,NULL,NULL,1,90,0);
INSERT INTO "transactions" VALUES(90,'2026-07-23',1,'Visa  100021  Vipps:toke Brygge Cafe Og',-50.0,8,0,0,'toke Brygge Cafe Og',NULL,NULL,1,91,0);
INSERT INTO "transactions" VALUES(91,'2026-07-25',1,'Overføring  9230000000 Vetle Nyhus Dahl KinoTpp: Vipps Mobilepay AS',-180.0,26,0,0,'Vetle Nyhus Dahl KinoTpp',NULL,NULL,1,92,0);
INSERT INTO "transactions" VALUES(92,'2026-07-25',1,'Overføring  92400000000 Ingvild Kvamme Berg Mat Og SnacksTpp: Vipps',100.0,5,0,0,'Ingvild Kvamme Berg Mat',NULL,NULL,1,93,0);
INSERT INTO "transactions" VALUES(93,'2026-07-25',1,'Giro  392 Statens Lånekasse For Utdannin AvtalegiroTerminbeløp Jul. 2026',-2468.0,31,0,0,NULL,NULL,NULL,1,94,0);
INSERT INTO "transactions" VALUES(94,'2026-07-25',1,'Overføring Innland  401 Øyvind Stene Lunde BetalingTpp: Vipps Mobilepay AS',-150.0,36,0,1,NULL,NULL,NULL,1,95,0);
INSERT INTO "transactions" VALUES(95,'2026-07-26',1,'Varekjøp Plantehallen Av Lørenveien 6 Oslo Dato 26.07 kl. 16.35',-200.0,16,0,0,NULL,NULL,NULL,1,96,0);
INSERT INTO "transactions" VALUES(96,'2026-07-26',1,'Varekjøp Joker Hasle St. Jørgens Oslo Dato 26.07 kl. 15.11',-35.28,5,0,0,NULL,NULL,NULL,1,97,0);
INSERT INTO "transactions" VALUES(97,'2026-07-24',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 24.07 kl. 19.16',-65.6,5,0,0,NULL,NULL,NULL,1,98,0);
INSERT INTO "transactions" VALUES(98,'2026-07-25',1,'Varekjøp Spar Dælenengga Dælenenggata Oslo Dato 25.07 kl. 17.39',-148.6,5,0,0,NULL,NULL,NULL,1,99,0);
INSERT INTO "transactions" VALUES(99,'2026-07-25',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 25.07 kl. 11.22',-135.9,5,0,0,NULL,NULL,NULL,1,100,0);
INSERT INTO "transactions" VALUES(100,'2026-07-25',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 25.07 kl. 12.44',-35.9,5,0,0,NULL,NULL,NULL,1,101,0);
INSERT INTO "transactions" VALUES(101,'2026-07-26',1,'Varekjøp Tilt . Oslo Dato 26.07 kl. 18.38',-262.0,9,0,0,NULL,NULL,NULL,1,102,0);
INSERT INTO "transactions" VALUES(102,'2026-07-26',1,'Varekjøp Circle k Økern Østre Aker v Oslo Dato 26.07 kl. 13.22',-51.9,12,0,0,NULL,NULL,NULL,1,103,0);
INSERT INTO "transactions" VALUES(103,'2026-07-26',1,'Varekjøp Bastard Burger Torggata 18 Oslo Dato 26.07 kl. 17.42',-258.0,8,0,0,NULL,NULL,NULL,1,104,0);
INSERT INTO "transactions" VALUES(104,'2026-07-27',1,'Kontoregulering  245 Mobil Overføring',12785.0,3,1,0,NULL,NULL,NULL,1,105,0);
INSERT INTO "transactions" VALUES(105,'2026-07-27',1,'Kontoregulering  246 Mobil Overføring',800.0,3,1,0,NULL,NULL,NULL,1,106,0);
INSERT INTO "transactions" VALUES(106,'2026-07-27',1,'Overføring Innland  403 Nordvest Teknikk AS Mobil BetalingDividend Kasper Aalborg',-800.0,35,1,0,NULL,NULL,NULL,1,107,0);
INSERT INTO "transactions" VALUES(107,'2026-07-24',1,'Visa  100021  Mer Norway AS',-280.55,12,0,0,'Mer Norway AS',NULL,NULL,1,108,0);
INSERT INTO "transactions" VALUES(108,'2026-07-24',1,'Visa  100121  Ecom Capital AS',-210.0,37,0,1,'Ecom Capital AS',NULL,NULL,1,109,0);
INSERT INTO "transactions" VALUES(109,'2026-07-24',1,'Visa  100221  Vipps:tor Bolle Waage',-120.0,36,0,1,'tor Bolle Waage',NULL,NULL,1,110,0);
INSERT INTO "transactions" VALUES(110,'2026-07-27',1,'Varekjøp All In One AS Skjeringen Stavanger Dato 27.07 kl. 18.20',-55.04,5,0,0,NULL,NULL,NULL,1,111,0);
INSERT INTO "transactions" VALUES(111,'2026-07-27',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 27.07 kl. 18.07',-176.6,5,0,0,NULL,NULL,NULL,1,112,0);
INSERT INTO "transactions" VALUES(112,'2026-07-28',1,'Overføring  92500000000 Ingvild Kvamme Berg MatTpp: Vipps',80.0,5,0,0,'Ingvild Kvamme Berg MatTpp',NULL,NULL,1,113,0);
INSERT INTO "transactions" VALUES(113,'2026-07-28',1,'Overføring  9260000000 Ingvild Kvamme Berg BokTpp: Vipps Mobilepay AS',-166.0,29,0,0,'Ingvild Kvamme Berg BokTpp',NULL,'book bought as a present for mother; split three ways with siblings',1,114,0);
INSERT INTO "transactions" VALUES(114,'2026-07-28',1,'Overføring  92700000000 Ingvild Kvamme Berg Tpp: Vipps',141.5,36,0,1,'Ingvild Kvamme Berg Tpp',NULL,NULL,1,115,0);
INSERT INTO "transactions" VALUES(115,'2026-07-28',1,'Overføring  92800000000 Torkel Aalborg BokTpp: Vipps',55.0,29,0,0,'Torkel Aalborg BokTpp',NULL,'Torkel'' share of the present for mother',1,116,0);
INSERT INTO "transactions" VALUES(116,'2026-07-28',1,'Overføring Sindre Aalborg Gave Til MammaRef:',55.0,29,0,0,NULL,NULL,NULL,1,117,0);
INSERT INTO "transactions" VALUES(117,'2026-07-29',1,'Kontoregulering  244 Ukespenger',2200.0,3,1,0,NULL,NULL,NULL,1,118,0);
INSERT INTO "transactions" VALUES(118,'2026-07-28',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 28.07 kl. 16.27',-63.9,5,0,0,NULL,NULL,NULL,1,119,0);
INSERT INTO "transactions" VALUES(119,'2026-07-28',1,'Visa  100021  Dominos',-283.0,8,0,0,NULL,NULL,NULL,1,120,0);
INSERT INTO "transactions" VALUES(120,'2026-07-29',1,'Varekjøp Rema Lorenveien Lørenveien 3 Oslo Dato 29.07 kl. 16.37',-102.68,5,0,0,NULL,NULL,NULL,1,121,0);
INSERT INTO "transactions" VALUES(121,'2026-07-29',1,'Visa  100021  Zettle_:lege Midhat Re',-299.0,20,0,0,NULL,NULL,NULL,1,122,0);
INSERT INTO "transactions" VALUES(122,'2026-07-30',1,'Varekjøp Kontroll_datter Grønland 10 Oslo Dato 30.07 kl. 18.28',-194.0,9,0,0,NULL,NULL,NULL,1,123,0);
INSERT INTO "transactions" VALUES(123,'2026-07-30',1,'Varekjøp Kontroll_datter Grønland 10 Oslo Dato 30.07 kl. 19.07',-112.0,9,0,0,NULL,NULL,NULL,1,124,0);
INSERT INTO "transactions" VALUES(124,'2026-06-10',2,'IBSEN TANNKLINIKK/ TAN, OSLO',-1350.0,18,0,0,NULL,NULL,NULL,2,3,0);
INSERT INTO "transactions" VALUES(125,'2026-06-10',2,'Vipps*Sumo Solli Plass, Oslo',-269.0,8,0,0,'Sumo Solli Plass',NULL,NULL,2,4,0);
INSERT INTO "transactions" VALUES(126,'2026-06-11',2,'Innbetaling',2156.0,4,1,0,NULL,NULL,NULL,2,5,0);
INSERT INTO "transactions" VALUES(127,'2026-06-11',2,'Innbetaling',1350.0,4,1,0,NULL,NULL,NULL,2,6,0);
INSERT INTO "transactions" VALUES(128,'2026-06-11',2,'Innbetaling',797.0,4,1,0,NULL,NULL,NULL,2,7,0);
INSERT INTO "transactions" VALUES(129,'2026-06-14',2,'BOLT.EU/O/9010000000, Tallinn, EST',-375.0,11,0,0,NULL,NULL,NULL,2,8,0);
INSERT INTO "transactions" VALUES(130,'2026-06-15',2,'Vipps*Bjarte Lunde Sk, Oslo',-350.0,36,0,1,'Bjarte Lunde Sk',NULL,NULL,2,9,0);
INSERT INTO "transactions" VALUES(131,'2026-06-17',2,'Vipps*Anders Vestli B, Oslo',-270.0,36,0,1,'Anders Vestli B',NULL,NULL,2,10,0);
INSERT INTO "transactions" VALUES(132,'2026-06-17',2,'KID 47147 STORO, Oslo',-305.9,15,0,0,NULL,NULL,NULL,2,11,0);
INSERT INTO "transactions" VALUES(133,'2026-06-28',2,'Vipps*VY App, Oslo',-658.0,10,0,0,'VY App',NULL,NULL,2,12,0);
INSERT INTO "transactions" VALUES(134,'2026-06-29',2,'KONDOMERIET AS, Oslo',-359.0,17,0,0,NULL,NULL,NULL,2,13,0);
INSERT INTO "transactions" VALUES(135,'2026-06-29',2,'Innbetaling',5433.54,4,1,0,NULL,NULL,NULL,2,14,0);
INSERT INTO "transactions" VALUES(136,'2026-06-29',2,'REMA 1000 LORENVEIEN, OSLO',-99.32,5,0,0,NULL,NULL,NULL,2,15,0);
INSERT INTO "transactions" VALUES(137,'2026-06-29',2,'SPORT OUTLET KA, Oslo',-2113.0,14,0,0,NULL,NULL,NULL,2,16,0);
INSERT INTO "transactions" VALUES(138,'2026-06-30',2,'PROUD MARY OSLO, Oslo',-238.0,7,0,0,NULL,NULL,NULL,2,17,0);
INSERT INTO "transactions" VALUES(139,'2026-06-30',2,'PROUD MARY OSLO, Oslo',-119.0,7,0,0,NULL,NULL,NULL,2,18,0);
INSERT INTO "transactions" VALUES(140,'2026-06-30',2,'PROUD MARY OSLO, Oslo',-238.0,7,0,0,NULL,NULL,NULL,2,19,0);
INSERT INTO "transactions" VALUES(141,'2026-06-30',2,'Proud Mary Oslo, Kristiansand',-259.0,7,0,0,NULL,NULL,NULL,2,20,0);
INSERT INTO "transactions" VALUES(142,'2026-06-30',2,'PROUD MARY OSLO, Oslo',-119.0,7,0,0,NULL,NULL,NULL,2,21,0);
INSERT INTO "transactions" VALUES(143,'2026-06-30',2,'KEBAB BITEN AS, OSLO',-380.0,8,0,0,NULL,NULL,NULL,2,22,0);
INSERT INTO "transactions" VALUES(144,'2026-07-01',2,'Innbetaling',1656.32,4,1,0,NULL,NULL,NULL,2,23,0);
INSERT INTO "transactions" VALUES(145,'2026-07-01',2,'Innbetaling',1080.0,4,1,0,NULL,NULL,NULL,2,24,0);
INSERT INTO "transactions" VALUES(146,'2026-07-01',2,'AVD.47 BAKER NO, OSLO',-204.0,7,0,0,NULL,NULL,NULL,2,25,0);
INSERT INTO "transactions" VALUES(147,'2026-07-01',2,'Vipps*Eirik Tangen, Oslo',-270.0,36,0,1,'Eirik Tangen',NULL,NULL,2,26,0);
INSERT INTO "transactions" VALUES(148,'2026-07-01',2,'Vipps*Jonas Vestli B, Oslo',-270.0,36,0,1,'Jonas Vestli B',NULL,NULL,2,27,0);
INSERT INTO "transactions" VALUES(149,'2026-07-01',2,'Vipps*Trygve Solheim H, Oslo',-270.0,36,0,1,'Trygve Solheim H',NULL,NULL,2,28,0);
INSERT INTO "transactions" VALUES(150,'2026-07-01',2,'Vipps*Halvard Stene M, Oslo',-270.0,36,0,1,'Halvard Stene M',NULL,NULL,2,29,0);
INSERT INTO "transactions" VALUES(151,'2026-07-04',2,'REMA 1000 LORENVEIEN, OSLO',-726.63,5,0,0,NULL,NULL,NULL,2,30,0);
INSERT INTO "transactions" VALUES(152,'2026-07-04',2,'SPORT OUTLET, Oslo',-1085.0,14,0,0,NULL,NULL,NULL,2,31,0);
INSERT INTO "transactions" VALUES(153,'2026-07-04',2,'JOKER LØREN STA, Oslo',-256.73,5,0,0,NULL,NULL,NULL,2,32,0);
INSERT INTO "transactions" VALUES(154,'2026-07-05',2,'Vipps*Fly Chicken App, Oslo',-360.0,8,0,0,'Fly Chicken App',NULL,NULL,2,33,0);
INSERT INTO "transactions" VALUES(155,'2026-07-06',2,'VEIKROA NES I Å, Nes I AAdal',-244.0,8,0,0,NULL,NULL,NULL,2,34,0);
INSERT INTO "transactions" VALUES(156,'2026-07-06',2,'7-ELEVEN LANGS VEI 758, NES I ADAL',-47.9,6,0,0,NULL,NULL,NULL,2,35,0);
INSERT INTO "transactions" VALUES(157,'2026-07-06',2,'Uno-X 71056 Nes i AAda, Nes I AAdal',-135.37,12,0,0,NULL,NULL,NULL,2,36,0);
INSERT INTO "transactions" VALUES(158,'2026-07-06',2,'Rabatt varekjøp ladestasjon',10.83,12,0,0,NULL,NULL,NULL,2,37,0);
INSERT INTO "transactions" VALUES(159,'2026-07-07',2,'Vipps*DNT-Den Norske T, Oslo',-860.0,25,0,0,'DNT-Den Norske T',NULL,NULL,2,38,0);
INSERT INTO "transactions" VALUES(160,'2026-07-07',2,'Leirvassbu Turi, Lesjaskog',-1280.0,27,0,0,NULL,NULL,NULL,2,39,0);
INSERT INTO "transactions" VALUES(161,'2026-07-07',2,'Leirvassbu Turi, Lesjaskog',-120.0,27,0,0,NULL,NULL,NULL,2,40,0);
INSERT INTO "transactions" VALUES(162,'2026-07-08',2,'Vipps*VY App, Oslo',320.0,10,0,0,'VY App',NULL,NULL,2,41,0);
INSERT INTO "transactions" VALUES(163,'2026-07-08',2,'Vipps*Morgenbladet AS, Oslo',-10.0,24,0,0,'Morgenbladet AS',NULL,NULL,2,42,0);
INSERT INTO "transactions" VALUES(164,'2026-07-08',2,'Leirvassbu Turi, Lesjaskog',-105.0,27,0,0,NULL,NULL,NULL,2,43,0);
INSERT INTO "transactions" VALUES(165,'2026-07-08',2,'Leirvassbu Turi, Lesjaskog',-45.0,27,0,0,NULL,NULL,NULL,2,44,0);
INSERT INTO "transactions" VALUES(166,'2026-07-08',2,'Leirvassbu Turi, Lesjaskog',-38.0,27,0,0,NULL,NULL,NULL,2,45,0);
INSERT INTO "transactions" VALUES(167,'2026-07-20',2,'Innbetaling',4982.8,4,1,0,NULL,NULL,NULL,3,3,0);
INSERT INTO "transactions" VALUES(168,'2026-07-30',2,'Mol*Hoome AS, 4799000000',-13990.0,15,0,0,NULL,NULL,NULL,3,4,0);
INSERT INTO "transactions" VALUES(169,'2026-07-31',2,'BOLT.EU/P/9290000000, Tallinn, EST',-25.0,11,0,0,NULL,NULL,NULL,3,5,0);
INSERT INTO "transactions" VALUES(170,'2026-07-31',2,'MAULUND A/S, Risskov, DNK',-298.0,37,0,1,NULL,NULL,NULL,3,6,0);
INSERT INTO "transactions" VALUES(171,'2026-08-01',2,'BOLT.EU/R/9300000000, Tallinn, EST',-29.18,11,0,0,NULL,NULL,NULL,3,7,0);
INSERT INTO "transactions" VALUES(172,'2026-08-02',2,'JOKER LØREN STA, Oslo',-97.87,5,0,0,NULL,NULL,NULL,3,8,0);
INSERT INTO "transactions" VALUES(173,'2026-08-06',2,'Innbetaling',14440.05,4,1,0,NULL,NULL,NULL,3,9,0);
INSERT INTO "transactions" VALUES(174,'2026-08-08',2,'VOLT 285, Oslo',-1022.5,13,0,0,NULL,NULL,NULL,3,10,0);
INSERT INTO "transactions" VALUES(175,'2026-08-08',2,'EURO SKO STORO, 0485 OSLO',-999.0,13,0,0,NULL,NULL,NULL,3,11,0);
INSERT INTO "transactions" VALUES(176,'2026-08-08',2,'BOYS STORO, OSLO',-449.4,13,0,0,NULL,NULL,NULL,3,12,0);
INSERT INTO "transactions" VALUES(177,'2026-08-09',2,'Vipps*Ingvild Kvamme B, Oslo',-89.0,36,0,1,'Ingvild Kvamme B',NULL,NULL,3,13,0);
INSERT INTO "transactions" VALUES(178,'2026-08-09',2,'VYGRUPPEN AS, OSLO',-678.0,10,0,0,NULL,NULL,NULL,3,14,0);
INSERT INTO "transactions" VALUES(179,'2026-08-09',2,'JOKER LØREN STA, Oslo',-163.7,5,0,0,NULL,NULL,NULL,3,15,0);
INSERT INTO "transactions" VALUES(180,'2026-07-20',1,'Lån  422687 Lån 1516.09.18257 Avdrag Kr 3.407,26Renter Kr 9.816,49  [interest]',-9816.49,32,0,0,NULL,NULL,'split from source row 69',1,69,1);
INSERT INTO "transactions" VALUES(181,'2026-07-20',1,'Lån  422687 Lån 1516.09.18257 Avdrag Kr 3.407,26Renter Kr 9.816,49  [principal]',-3407.26,34,1,0,NULL,NULL,'split from source row 69',1,69,1);
INSERT INTO "transactions" VALUES(182,'2026-07-20',1,'Lån  422687 Lån 1516.09.18257 Avdrag Kr 3.407,26Renter Kr 9.816,49  [fees]',-65.0,33,0,0,NULL,NULL,'split from source row 69',1,69,1);
CREATE INDEX idx_tx_date     ON transactions(date);
CREATE INDEX idx_tx_category ON transactions(category_id);
CREATE INDEX idx_tx_review   ON transactions(needs_review);
CREATE VIEW v_spending AS
SELECT c.name AS category, ROUND(SUM(-t.amount), 2) AS spent, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'expense'
GROUP BY c.name ORDER BY spent DESC;
CREATE VIEW v_income AS
SELECT c.name AS category, ROUND(SUM(t.amount), 2) AS received, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'income'
GROUP BY c.name ORDER BY received DESC;
CREATE VIEW v_needs_review AS
SELECT t.date, a.name AS account, t.description, t.amount, c.name AS guessed_category
FROM transactions t
JOIN accounts a ON a.id = t.account_id
LEFT JOIN categories c ON c.id = t.category_id
WHERE t.needs_review = 1 ORDER BY t.date;
COMMIT;
