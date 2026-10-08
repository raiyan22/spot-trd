# Sharia screening notes for the research universe (2026-10-02)

**Purpose:** document what each candidate is and where the concerns are, so that *you* can make the religious judgment.
I am not issuing a ruling on any asset. Nothing here changes what the system trades: only BTC is enabled. The other four
are "pending" in `config/sharia_screen.yaml` and are used for research only. The universe test treats eligibility as a
filter that comes first; no asset was chosen because of its backtest.

## 1. How reliable are the sources?

- **Primary-style source used:** the Shariyah Review Bureau (SRB) paper *The Shariah factor in Cryptocurrencies and Tokens*
  (2018), [PDF](https://shariyah.net/wp-content/uploads/2021/05/The-Shariah-factor-in-Cryptocurrencies-and-Tokens.pdf).
  I read it in full. It is a methodology paper, not a fatwa ("by no means a definitive conclusion or fatwa", its own words),
  and it dates from 2018.
- **Everything else I found is secondary:** commercial "is X halal?" sites (Sharlife, CoinStudy, Crypto Ummah, Halal Wallet,
  Zakat Invest and similar) with uneven methods, no named scholars on many pages, and obvious commercial incentives. They
  disagree with each other (for example, Solana is "halal" on one and "doubtful" on another). I used them only to show that
  disagreement exists, never as a deciding source.
- Claims I could **not** verify, so treat them as unconfirmed: that Mufti Taqi Usmani has ruled crypto impermissible (one
  search summary said so; the article it came from did not name him); a news item saying the SRB certified XRP specifically
  (the SRB paper itself contains no per-coin certificates); a 2019 "Ethereum is halal" scholars' paper reported by news sites
  (I did not locate the document).
- General positions reported by a survey article (also uncited to primary texts): permissive (Mufti Faraz Adam, Southeast Asian
  fatwa councils), conditional (AAOIFI is described as still developing standards), prohibitive (Egypt's Grand Mufti, Turkey's
  Diyanet, some Hanafi scholars, mainly citing gharar, speculation and lack of intrinsic value).

## 2. The methodology applied (SRB, plus the usual prohibitions)

From the SRB paper, as I read it:

- Coins that act as peer-to-peer money (it names Bitcoin, **Litecoin**, Ripple) are treated as currency through custom
  (`'urf`): wide acceptance for Bitcoin, "exclusive custom" within their own network for the others.
- Utility and work tokens are rights (`huquq 'urfiyyah`) that may be traded on a secondary market "**provided that the project
  is Shariah compliant** and has passed the Shariah screening".
- Its conclusion: invest only in tokens that passed a screening of the project's core business activity and what the token
  represents.

Operational checklist (C1-C8 in `config/sharia_screen.yaml`): spot ownership only, no yield mechanism in the token, genuine
utility, permissible core business, ecosystem flagged rather than ignored, no issuer return promises, not a meme, held in your
own spot balance with no Earn products.

The contested point is C5 for smart-contract platforms. SRB's "provided that the project is Shariah compliant" is easy to
satisfy for a payment coin and hard to settle for a platform that anyone can build on. Scholars differ on whether holding the
platform's gas token is judged by the token's own function or by what gets built on top.

## 3. Candidates

TVL figures below are from [DefiLlama](https://api.llama.fi/protocols) on 2026-10-02 (saved in
`data/raw/defillama_tvl_by_category.json`). They are a crude proxy: TVL double counts some staking and bridging, and it
measures money parked in apps, not users or fees. "Non-exchange" excludes the CEX-reserve category.

| | BTC | ETH | SOL | ADA | LTC |
|---|---|---|---|---|---|
| Non-exchange TVL | $35.4B | $171.9B | $17.7B | $0.08B | $0.01B |
| Lending-type share (lending, CDP, leveraged farming) | 0.1% | 23.5% | 16.8% | 30.5% | 0% |
| Derivatives-type share | 0% | 3.9% | 6.8% | 2.3% | 0% |
| Staking-type share | 13.4% | 41.0% | 48.5% | 1.0% | 0% |

### BTC (already in your universe)
- **What it is:** proof-of-work payment and store-of-value network; no issuer; no smart-contract ecosystem at the base layer.
- **Utility:** medium of exchange / value storage (SRB's "currency coin" category).
- **Ecosystem:** the large "TVL" is mostly bridged or wrapped BTC used elsewhere, not protocol activity.
- **Concerns:** none specific to the coin beyond the general disagreement about crypto as money (section 4).
- **Flag:** low.

### ETH
- **What it is:** general smart-contract platform. ETH pays transaction fees (gas) and is staking collateral.
- **Utility:** real and necessary (gas).
- **Ecosystem:** interest-based lending and borrowing is about a quarter of non-exchange TVL, plus stablecoin CDPs, derivatives and
  basis trading; also gambling, NFT and meme-token activity (not measured here).
- **Concerns:** the platform proviso (C5). Holding ETH spot is not lending; but part of ETH's value reflects demand from those uses.
  Staking is a separate question and the system never stakes.
- **Disagreement:** secondary sources mostly call spot ETH permissible; some separate the token from the apps, others do not.
- **Flag:** medium. Needs your decision.

### SOL
- **What it is:** high-throughput smart-contract platform (proof of stake plus a time-ordering mechanism called proof of history).
- **Utility:** real (fees, staking).
- **Ecosystem:** lending about 17% and derivatives about 7% of non-exchange TVL; Solana has also been the main venue for
  meme-token launches (not quantified here). Known history of large early insider and exchange-affiliated holdings (a
  centralisation/gharar point some reviewers raise).
- **Disagreement:** aggregator verdicts split between "halal", "neutral" and "doubtful".
- **Flag:** medium to high. Needs your decision.

### ADA
- **What it is:** proof-of-stake smart-contract platform; smart contracts arrived in 2021.
- **Utility:** real but modest (fees, staking, governance).
- **Ecosystem:** tiny: $0.08B non-exchange TVL, of which lending-type is about 30% of a very small base.
- **Disagreement:** aggregators mostly call it permissible; same platform proviso as ETH.
- **Flag:** low to medium. Needs your decision.

### LTC
- **What it is:** proof-of-work payment coin forked from Bitcoin; no smart-contract ecosystem.
- **Utility:** payments; SRB names Litecoin explicitly among currency coins, noting it is not accepted by large merchants but
  functions as medium of exchange inside its own network.
- **Ecosystem:** essentially no DeFi.
- **Concerns:** limited real adoption (gharar/speculation argument applies as it does to any coin); an optional
  confidential-transaction extension (MWEB), which some reviewers dislike for illicit-use risk.
- **Flag:** low. Needs your decision.

### Why LTC is the fifth slot
You asked for one more established non-meme asset. I chose LTC **before running the portfolio test**, on screening grounds
only: oldest of the non-platform coins, a currency coin in SRB's own list, no DeFi or meme ecosystem. For transparency: I had
already run a one-off exploratory pass of eight liquid pairs on the unmodified strategy to see whether the rules behave
differently outside BTC (ETH, BNB, XRP, ADA, LTC, LINK, DOGE, SOL). That table is not used anywhere in the decision, and LTC
turned out to be one of the weakest performers in it, which is some evidence the choice was not performance-driven.

Alternatives I considered and **did not test**, with the reason you may care:
- **XRP:** payments coin controlled by a company with large escrowed supply; centralisation and regulatory history. SRB lists
  "Ripple" as a currency coin, but I could not verify any per-coin certificate.
- **LINK:** oracle token whose main customers are DeFi protocols including lending: strong C5 concern.
- **BNB:** exchange token tied to Binance, which itself offers interest-bearing Earn products, and BNB Chain hosts DeFi lending:
  strong C2/C5 concern for an interest-free policy.
- **DOGE and other meme coins:** excluded by C7.

## 4. Scholarly disagreement in one paragraph

Whether crypto is *mal* (property) and usable as money is itself disputed. Permissive views rely on custom and utility (the SRB
approach). Prohibitive views cite gharar, speculation, lack of backing or intrinsic value, and use in illicit finance. Even among
permitters, staking rewards and DeFi yield are treated differently from spot ownership. If you follow a school or scholar who
rejects crypto as an asset class, every row above is "rejected" and the answer for the system is to hold USDT only.

## 5. What I need from you

For each of ETH, SOL, ADA, LTC, set `user_decision` in `config/sharia_screen.yaml` to `approved`, `rejected`, or leave `pending`.
If you add the criteria you want enforced (for example "exclude any platform where lending-type activity exceeds X% of its
ecosystem"), I will encode them in that file. Separately, an approved symbol must also be added to `allowed_symbols` in
`config/halal_universe.yaml`; the test suite fails if a tradable symbol lacks an approved record.
