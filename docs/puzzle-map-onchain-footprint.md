# PUZZLE MAP — Jonathan Combs' On-Chain Footprint (Base + Multichain)

**Investigation date:** 2026-09-19 · **Method:** read-only throughout (public RPC, Blockscout API, page-text fetch, local CSV analysis). No wallet connected, nothing signed.
**Labels:** [CONFIRMED] = verified via RPC/API/page output · [INFERRED] = reasoned, not directly verified · [UNKNOWN] = could not verify.

## Corrections to earlier analysis
1. The 10,000-row dataset is `export-filtered-txs-2026-05-17-04-51-42.csv` — the file named `Ethereum_token_transfers_0xC9f1…csv` is headers-only (verified with `wc -l`).
2. The mystery hex `0xb20000…` was first misread as truncated calldata (a byte miscount). It is a **complete 20-byte address** — see verdict below.

---

## 1. ENTITY LIST

### The user's cluster
| # | Address / name | What it is | Holdings / activity | Confidence |
|---|---|---|---|---|
| U1 | `0x20fbc02bcf1d49f4cf20410f3df7b7ecf9d0f910` — `jonathancombs.base.eth` | Coinbase Smart Wallet (ERC-4337 proxy) | 0.002528578392961399 ETH (~$6.65); 200,000,000 BA; 1.246 vAMM-WETH/BA LP; 3,623.23 YUP (~$1); 0.00133 USDC; 0.704 WELL; ~45 spam-dust entries ($0) | CONFIRMED |
| U2 | `0x7674ffb3e82059d03c113a89874d5328ecc9d73e` | EOA, owner of U1 (factory `AccountCreated` event) | 0 ETH, 0 txs on Base/mainnet/OP/Arbitrum | CONFIRMED |
| U3 | `0xaba79af383a84527223cff2e994a16787f4b71ad` | EOA, owner of U1 (same source) | 0 ETH, 0 txs on Base/mainnet/OP/Arbitrum | CONFIRMED |
| U4 | `0xBA5ED110eFDBa3D005bfC882d75358ACBbB85842` | CoinbaseSmartWalletFactory (verified) | Deployed U1 via CREATE2 | CONFIRMED |
| U5 | `0xaf2bfb6b69dfe6efd257fe8cd694175156a23812` | EOA — professional ERC-4337 bundler/sponsor | ~14.51 ETH, nonce 5,391,429, submitting bundles as of 2026-09-19 | CONFIRMED |
| U6 | `0x739120AdE7ED878FcA5bbDB806263a8258FE2360` — "Coinbase 22" | EOA — Coinbase exchange hot wallet (withdrawal processor) | ~103 ETH, ~1.94M nonce, ~782k txs | CONFIRMED |
| U7 | `0xb200000000000000000000a921e8D39930F83bff` — "Base" (BA) | **B20 Asset-variant token** (Base native standard), 18 dec | totalSupply 200,031,052; live (`name()="Base"`, `symbol()="BA"`); user holds 200,000,000 | CONFIRMED |
| U8 | `0xBc78363645702488F6897504E27374B53678eAD1` | Aerodrome vAMM WETH/BA pool (EIP-1167 proxy) | User is sole LP (1.246 LP tokens); received 31,052 BA on 2026-08-24 | CONFIRMED |
| U9 | `0xB20f000000000000000000000000000000000000` | B20 factory precompile (chain-level) | Called by U1 to mint BA | CONFIRMED |
| U10 | `0x01CCF4941298a0b5AC4714c0E1799a2dF8387048` — YUP | Real Yup token (yup.io), 18 dec | User holds 3,623.23 (~$1); ~9,044 holders; thin liquidity | CONFIRMED |
| U11 | `0x15A8c3098ff6260952Fc99f420D89ed705c5C08E` | Unidentified 81-byte contract | Received 4.006698 USDC + 0.00171 ETH (~$8) from U1 on 2026-05-09 | CONFIRMED (existence/flow); purpose UNKNOWN |
| U12 | `0x50Abbd64734B96101dAAc37Ff1bDDB45FdaC213b` | Sibling smart wallet, same 2026-01-04 onboarding bundle, different owners | 0 ETH; 12 inbound NFTs on 2026-05-15 | CONFIRMED; INFERRED to be another user's wallet |

### The May-17 pool cluster (separate — see verdict)
| # | Address | What it is | Role in data |
|---|---|---|---|
| P1 | `0x4e962BB3889Bf030368F56810A9c96B83CB3E778` | **Aerodrome SlipStream cbBTC/USDC 0.05% pool** (public DEX, created 2024-09-12, TVL ~$5.7M) | In all 10,000 rows as from *or* to — it's the venue, not an actor |
| P2 | `0xCf7603eB05d36B54935feCb6c5f79e6d1198F1c3` | Unverified 257-byte executor contract (45 clones share bytecode — factory template) | 7,106/10,000 transfers; net −$77,594 on ~$404M gross |
| P3 | `0x2ac57AE4ac5d6BBA822A903377E655aa607Ff0A3` | EOA, sole caller of P2; nonce 2,569,612; ~0.002 ETH; WETH sweep pattern | INFERRED: professional HFT/searcher operator |
| P4 | `0xb300000b72deaeb607a12d5f54773d1c19c7028d` | Contract, labeled "Binance: DEX Router" in BscScan search results | Counterparty in the set |
| +76 | 76 other counterparties | 36 contracts / 11 EOAs / 33 unresolvable via public RPC | All interact only with P1 in-window |

### The oneworldonecoin lead (someone else)
| # | Address | What it is |
|---|---|---|
| W1 | `0x2c34bf9d0e32bcb9e21c489745e4d6f0bdc8837c` — `oneworldonecoin.base.eth` | Coinbase Smart Wallet (byte-identical proxy to U1, same implementation) — **different controllers**: owners `0x5d1762f73fca85078d14179c5a0b1bb6a96b5a22` + `0xfd22a8924a82eac34bea187dbaba2c5ce304e5eb` (both fresh, 0-tx EOAs). Created 2026-02-02; funded once with dust; ~25 micro-transfers mid-June 2026; dormant since. No on-chain link to U1, P1, or U7. |

**Infrastructure referenced:** EntryPoint v0.6 `0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789`; LI.FI Diamond `0x1231DEB6f5749EF6cE6943a275A1D3E7486F4EaE`; Relay depository `0x4cd00e387622c35bddb9b4c962c136462338bc31`; USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`; cbBTC `0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf`.

---

## 2. RELATIONSHIP GRAPH (in words)
- U1 was deployed 2026-01-04 by factory U4 inside a 7-userOp bundle submitted by bundler U5, gas-sponsored by paymaster `0x2faeb0760d4230ef2ac21496bb4f0b47d634fd4c`; the basename `jonathancombs.base.eth` was minted to U1 in the same bundle. Owners U2+U3 recorded at creation (both empty everywhere).
- U1's only meaningful funding: 0.00217011 ETH from Coinbase hot wallet U6 on 2026-05-01 (tx `0xa648668d325fa5365e810ec6dfa4b7d47c77a117b6d7041ebd482a6a9914ada2`) — i.e., a Coinbase exchange withdrawal, so a Coinbase account sits behind this wallet.
- U1 → LI.FI Diamond: ~16 tiny test swaps May–Aug 2026 (USDC lifetime IN 34.849728 / OUT 34.848398, net +$0.00133 — fully round-tripped). Two decoded in full: tx `0x3521d498ff6bbdf59dc77416f1d0b00d50f915a091d86b8d8e68e77b2936cb38` (2026-08-08) = 2 USDC → 0.0010329318 WETH → Relay bridge to **BNB Chain (chain 56), receivable at the same address**; tx `0xdf32e008f83ce6aab6bcd1562873a79b6c4e256aa958522104331ef4d5e0352c` (2026-08-08) = 0.949036 USDC → 3,623.23 YUP, same-chain swap. Both initiated via Base App (`integrator="base-app"`), 1% LI.FI fee.
- U1 → B20 factory U9 on 2026-08-24 (tx `0x10f63e6cdbbc8855ba3779ac4a48aba817138befa9f32c6c6a242d45616adefe`, UserOp nonce 348): **minted 200,031,052 BA** to itself. 34 seconds later (tx `0xaecbaa36e576c764aa404a0e00a31fd35bba3d8b2dd33b6166114883ba389aa5`, nonce 351): 31,052 BA + 0.00005 ETH into pool U8 via `Router.addLiquidityETH`; U1 received 1.246 LP tokens (sole LP).
- U1 → U11: ~$8 on 2026-05-09 (purpose unknown).
- U1 has **zero** edges to P1/P2/P3, the CSV cluster, or W1 (disjoint owners, funders, counterparties — all checkable intersections empty).
- W1 is infrastructure-identical to U1 (same proxy bytecode, same implementation) but disjoint controllers/funders — a different person's wallet from the same Coinbase Smart Wallet lineage.

---

## 3. TIMELINE OF THE USER'S ON-CHAIN LIFE
| Date | Event | Evidence |
|---|---|---|
| 2026-01-04 03:46:31Z | U1 deployed (block 40354522, tx `0xd1945462e8ec0928606b8ef43dc8db5d2de4c313aaa62903fa8f500daebc1082`); basename minted; gasless via paymaster | CONFIRMED (factory event + initCode) |
| 2026-05-01 | Funded 0.00217011 ETH from Coinbase 22 (U6) | CONFIRMED (tx `0xa648668d…`) |
| 2026-05-08 | ETH→USDC swap (0.00216150 ETH → 4.944878 USDC) | CONFIRMED |
| 2026-05-09 | 4.006698 USDC + 0.00171 ETH → U11 (unidentified contract) | CONFIRMED (flow); purpose UNKNOWN |
| 2026-05-17 05:57–08:50 UTC | 10,000-transfer CSV window on pool P1 — **user absent** | CONFIRMED (0 matches) |
| May–Aug 2026 | ~16 tiny LI.FI test swaps via Base App, all round-tripped | CONFIRMED |
| 2026-06-25 / 07-08 | B20 launches on Base mainnet (two threads report slightly different dates — both post-May) | INFERRED date; activation CONFIRMED |
| 2026-08-08 | Bridge $1.98 WETH → BNB Chain; swap $0.94 → 3,623 YUP | CONFIRMED (full tx hashes above) |
| 2026-08-24 | **BA memecoin launch**: mint 200,031,052 + LP seed | CONFIRMED (both tx hashes above) |
| 2026-09-01 | Last activity: inbound spam airdrop | CONFIRMED |
| 2026-09-19 | Balances: 0.002528578392961399 ETH (~$6.65); 200M BA; 1.246 LP; 3,623 YUP; dust | CONFIRMED (RPC) |

---

## 4. THE 0xb20000… VERDICT
**The string is the user's own B20 memecoin.** `0xb200000000000000000000a921e8D39930F83bff` is a complete, valid **B20 Asset-variant token address** ("Base"/"BA", 18 decimals, supply 200,031,052, live on-chain). It is not calldata — the `createB20` selector is `0x62975e6a` ≠ `0xb2000000`, and the string is exactly 20 bytes. The user (via wallet U1, through the Base App — not the Base Analytics app, hence the 0-launch profile there) minted essentially the entire supply on 2026-08-24 and seeded a pool. It has 2 holders, no liquidity, no price — a test launch, economically dead. It **cannot** relate to the May CSV data (B20 didn't exist on mainnet then) and appears in **neither** CSV. Confidence: ~95%. Only open item: the actual deployer salt/admin (derivation isn't invertible; neither U1 nor W1 holds admin/mint roles).

## 5. THE HUB VERDICT
**There is no bot hub.** P1 is the public Aerodrome SlipStream cbBTC/USDC pool; the 10,000 transfers are swap legs through it during a ~20× volume burst ($404.7M gross in 3 hours — likely a BTC-volatility-driven arbitrage frenzy). The bot-like actor is counterparty P2 (executor contract, 7,106/10,000 transfers) driven by EOA P3 (2.57M-nonce HFT profile) doing balanced, alternating arbitrage — net only −$77.6k on $404M gross. Not wash trading (78 distinct counterparties, organic size distribution), not a fund-hoarding wallet. **User connection: UNRELATED** — U1 appears 0 times in the dataset; no shared funder (U6 vs unknown), no shared creator (U4 vs Aerodrome deployer `0x509BBAF1…`), no shared counterparty in any checkable record. Touching that pool only means trading cbBTC/USDC — millions of addresses have.

---

## 6. EXPLAINED
- What the wallet is (Coinbase Smart Wallet, Jan-2026 gasless onboarding, basename in same bundle).
- Where its money came from (one Coinbase withdrawal) and where it went (round-tripped test swaps, $2 BNB bridge, $0.94 YUP buy, BA launch, gas).
- What the mystery hex is (user's own B20 memecoin, Aug 24).
- What the "hub" is (public DEX pool) and what the May-17 activity was (arb burst, user uninvolved).
- What oneworldonecoin.base.eth is (someone else's dormant smart wallet; no link to user).
- That the Base Analytics "0 launches" profile is consistent (user launched via Base App, not that app).

## 7. UNEXPLAINED / OPEN
1. **The other 2 multichain addresses** behind the ~$26.88 Blockscan figure — owner EOAs U2/U3 are empty on all chains checked. (The $2 WETH on BNB at U1's address is one candidate piece.)
2. **U11** (`0x15A8c3098ff6260952Fc99f420D89ed705c5C08E`) — what contract received ~$8 on 2026-05-09?
3. **Owner-slot anomaly** — U1's owner reads now revert though it signed a userOp on 2026-08-24 (possible post-Aug upgrade; threads found 2 vs 3 owners — unresolved discrepancy).
4. **BA token's actual deployer/admin** — derivation not invertible; neither U1 nor W1 holds roles.
5. **W1's controllers** (`0x5d1762…`, `0xfd22a8…`) and its June micro-transfer burst to `0xd14E…` — unknown humans/purpose.
6. **P3's funder** (bot operator's origin) — needs paid indexer or rendered Basescan history.
7. Whether the ~$2 WETH on BNB Chain was ever claimed.

---

## 8. NEXT STEPS (concrete checks for the user)
1. **Coinbase app → withdrawal history:** confirm the 2026-05-01 withdrawal of 0.00217011 ETH to `0x20fbc0…f910` — closes the funding loop.
2. **Base App → activity history:** look for the 2026-08-24 "Base (BA)" token creation + liquidity seed — confirms the memecoin launch was yours (it was wallet-signed, so it should be there).
3. **Base App → May 9, 2026 activity:** identify what `0x15A8c3…` was — the ~$8 outflow.
4. **Check BNB Chain:** `bscscan.com/address/0x20fbc02bcf1d49f4cf20410f3df7b7ecf9d0f910` — is the ~$2 WETH sitting there?
5. **Do you recognize "One World One Coin"?** The basename belongs to someone else on current evidence — yours, a friend's, or a stranger's idea?
6. **Blockscan portfolio view** to name the other 2 multichain addresses.

## 9. LIVE-RENDER CHECKLIST (JS-gated pages; exact URLs + extraction targets)
1. `https://blockscan.com/address/0x20fbc02bcf1d49f4cf20410f3df7b7ecf9d0f910` — multichain portfolio: the exact "3 addresses / ~$26.88" breakdown by address and chain. *(Single most important unresolved item.)*
2. `https://basescan.org/address/0xb200000000000000000000a921e8D39930F83bff` — B20 TokenTracker tab: holders, transfer history, any creator/deployer attribution.
3. `https://basescan.org/address/0x2c34bf9d0e32bcb9e21c489745e4d6f0bdc8837c` — full funder hash `0x94f33454…`, internal-tx counterparty `0xd14E…`, bundler address.
4. `https://basescan.org/address/0x4e962BB3889Bf030368F56810A9c96B83CB3E778` — full contract creator address; long-tail tx history.
5. `https://basescan.org/address/0xCf7603eB05d36B54935feCb6c5f79e6d1198F1c3` — contract creator of the executor template; any name tag.
6. `https://basescan.org/address/0x2ac57AE4ac5d6BBA822A903377E655aa607Ff0A3` — earliest transaction / first funder; any label.
7. `https://www.base.org/name/oneworldonecoin.base.eth` — on-chain activity feed content.
8. `https://basescan.org/address/0x15A8c3098ff6260952Fc99f420D89ed705c5C08E` — identify the $8-recipient contract.
9. `https://bscscan.com/address/0x20fbc02bcf1d49f4cf20410f3df7b7ecf9d0f910` — BNB Chain token balances.

---

## 10. LIVE-RENDER RESULTS (2026-09-19, via live block explorer reads)

### Blockscan multichain breakdown — SOLVED
The "~$26.88 across 3 addresses" figure is the **same address** (`0x20fbc0…f910`) across chains. Total net worth **$26.87**, 6 tokens, 4 chains with balances:
- **Ethereum:** 9.376867 USDS (USDS Stablecoin) — **$9.38** (34.9%)
- **Base:** 0.002529 ETH — **$6.63** (24.7%)
- **Optimism:** 6.039182 USDC.e (bridged USDC) — **$6.04** (22.5%)
- **BNB Chain:** 199.19911856 JTT (Justus Token) — **$2.47** (9.2%)
- **Base:** 3,623.23 YUP — **$1.49** (5.6%)
- **Optimism:** 0.859649 USDC — **$0.86** (3.2%)
28 other chains show $0.00. **New vs §3 timeline:** the USDS-on-Ethereum and USDC-on-Optimism holdings were not in the earlier Base-only trace — same address holds value on mainnet and Optimism via unknown prior activity.

### BA token page (Basescan) — CONFIRMED
`0xb20000…f83bff`: "Base (BA)", also labeled "B20 Token (Asset)", 18 decimals, max total supply 200,031,052, **2 holders**, price $0.00, reputation UNKNOWN. Holders: `jonathancombs.base.eth` 200,000,000 (99.9845%); pool contract `0xBc783636…78eAD1` 31,052 (0.0155%). Transfer history = exactly 2 transfers: mint (Null → user, 200,031,052, block 50374247) and LP seed (user → pool, 31,052, block 50374264), both "26 days ago". Contract creator: "N/A (System Contract)" — consistent with B20 precompile mint.

### U11 identified — Alchemy smart wallet, funds UNMOVED
`0x15A8c309…705c5C08E` is a **verified Alchemy ERC-4337 modular smart account** ("Alchemy: SemiModularAccount Bytecode"), created by "Alchemy: Account Factory" (`0xC4717530…72dd7E2f1`) ~232 days ago. The 2026-05-09 inbound from the user's wallet is confirmed: 0.00171 ETH (internal tx `0x05268d88…`) + 4.006698 USDC (token tx `0x674e2ab8…`). **Both amounts are still held, unspent.** Current holdings: 0.00171 ETH ($4.49) + $4.90 in tokens (USDC 4.006698, Venice Token, RaveDAO, Morpho, etc.). Same day also received 1.507473 RaveDAO inbound via Handle Ops from a different sender (`0x4e59cbda…`, truncated). OPEN: is this Alchemy wallet the user's (another onboarding) or someone else's?

### BNB Chain — correction: JTT, not WETH
`bscscan.com/address/0x20fbc0…f910`: 0 BNB. Sole holding: **199.19911856 Justus Token (JTT)**, $2.47 — delivered 42 days ago by "Relay: Router V3" via `Permit2Transfer` (tx `0xba35be92…`, block 114663658). The earlier "≈$2 WETH receivable" hypothesis is corrected: the Relay bridge delivered JTT, which is still sitting there.

### Remaining open threads
- Prior on-chain activity that placed USDS on Ethereum and USDC/USDC.e on Optimism at the user's address (pre-dates or sits outside the Base trace).
- Whether the Alchemy smart wallet (U11) belongs to the user.
- "One World One Coin" recognition (W1).

---

## 11. DEEPER DIG — MAINNET & OPTIMISM ORIGINS (2026-09-19, live explorer reads)

### Ethereum mainnet: exactly 1 transfer, ever
- 2026-08-07 (block 25700803): **9.376867 USDS** from "Coinbase 10" (`0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43`), tx `0x7663aff85b346dc4f5014d583c280dc0c932a8089fe85138afb8d03e3992ecaf`.
- The tx is a Coinbase batch ("Coinbase: Deposit") distributing small USDS payouts to 16+ recipients — the user's address was one leg. Not user-initiated.
- No ETH ever moved, no other tokens, no NFTs, no initiated transactions on mainnet. Earliest/only mainnet activity: 2026-08-07.

### Optimism: exactly 2 inbound transfers, both Across bridge fills from Base
- 2026-05-17 (block 151709442): **0.859649 USDC** via Across Spoke Pool (`0x6f26Bf09…`), tx `0xbcaa7f23c6191efdc0be25b6103882188317737f8ac1ce5abcf3b000f71c8fa2`; linked Base origin tx `0xb92c1058bc7aeb5dfc8ca49c43142f49984665fa3b30377cbf2233861bc381fe`.
- 2026-07-18 (block 154367967): **6.039182 USDC.e** via Across Spoke Pool, tx `0xd8fe62c9beb4a7f342823c06d6108de21cd9b09f28beb6b14c1f2f6c153de4e5`; linked Base origin tx `0x24dd887fed9d098bc7f7130c5f61c1a5dc98828aae4fa21b6d57bf821afaa6a7`.
- Both are user-initiated Base → Optimism bridges (Across). No outbound, no ETH, no NFTs. Earliest Optimism activity: 2026-05-17 (same day as the CSV arb-frenzy window — coincidence; different venue/mechanism).
- Note: the earlier Base-only trace counted LI.FI Diamond flows; these Across outflows sit outside it.

---

## 12. DEEPER DIG — ALCHEMY WALLET & ONEWORLDONECOIN HISTORIES (2026-09-19, live Basescan reads)

### U11 (Alchemy smart wallet) — verdict: IT'S THE USER'S
- Full history retrieved (0 normal txs initiated, 2 internal, 30 ERC-20 transfers — ALL inbound, never sent anything out).
- **First funder = the user's own wallet** `0x20fbc0…f910`: ~2026-03-30 (block 44020583), starting with 2 TSUKI (tx `0xf1394cb4…`), then in the same session: 1.341372 MT, 80,151.80517 TSUKI, 0.008683 MORPHO, 1.160427 WELL, 0.022363 VVV (Venice), 0.02085 KTA (Keeta) — a dust/small-token consolidation batch. **This March-30 activity window was absent from the earlier Base trace.**
- 2026-05-09: 4.006698 USDC + 0.00171 ETH + 1.507473 RAVE, all from the user's wallet (correction: the "0x4e59cbda…" string was a tx hash `0x4e59cbda…05ce8`, not a sender).
- Everything since: 20+ inbound spam airdrops only (Cyrus, Zama, Vow, Cole, Aurora, Leo, "RaveDAO." spoof with trailing period, etc.).
- RaveDAO (RAVE) contract `0x1aA8fD5B…fc3`, BaseScan tag "# Entertainment", links ravedao.com.
- Assessment: a purpose-built, receive-only Alchemy ERC-4337 smart account belonging to the user — likely created for RaveDAO/entertainment onchain use. Funds (USDC/ETH/RAVE) remain unspent.

### W1 (oneworldonecoin.base.eth) — verdict: SOMEONE ELSE'S, no user link
- First funders: `0x94f334549B6393c3BbbD89C505Da58b6884EF344` (0.000055 ETH, 2026-02-02, tx `0x4c61709a…`) and **suryaprakash.base.eth** (`0xB4BD7D410543cB27f42c562ab3fF5DC12fBDd42F`, 0.1 USDC).
- Owner swept the entire USDC (~0.1006) out in three Handle Ops to `0x49fb9C16…fD7E04` and `0xdc5d8200A030798BC6227240f68b4dD9542686ef`.
- Mid-June "burst" = 13 inbound micro-transfers ALL from `0xf5E37C435EE51D524F6CEFb0615B4Dab74f90DeA` via "Disperse Token S…" (mass-airdrop multisender tool) — spam, not real activity. Same sender did 3 more in Aug 2026 (sender prefix `0xd15fE25e…`, NOT the earlier-noted `0xd14E…` — no `0xd14E`-prefixed address exists anywhere in its 51 transfers).
- Also hit by labeled spam "Fake_Phishing4734884" dust at creation.
- Never made a normal transaction beyond creation funding. No on-chain link to the user.

---

## 13. THE TWO NEW ADDRESSES (2026-09-19)

### A1 = `0xffa3f8737c39e36dec4300b162c2153c67c8352f` — Aerodrome vAMM WETH/WELL pool
- Identified via 5 independent public codebases, not via explorer labels:
  - SmolDapp tokenLists `lists/8453/popular.json`: "Volatile AMM - WETH/WELL", symbol `vAMM-WETH/WELL`, chainId 8453
  - Beefy `src/data/base/aerodromeLpPools.json`: "aerodrome-weth-well", gauge `0xcEa0a2228145d0fD25dE083e3786ddB1eA184296`, lp0 = WETH (`0x4200…0006`), lp1 = WELL (`0xFF8adeC2221f9f4D8dfbAFa6B9a297d17603493D`)
  - Also referenced in tetu-liquidator, tetu-v2-strategies-polygon, contango core-v2, ovnstable-core-contracts (45 public code hits total)
- On-chain: 2,386 txns, heavy Approve + Claim Fees activity from many EOAs — consistent with normal LP-pool usage.
- Link to user: wallet holds **0.704 WELL**; moved **1.160427 WELL** on 2026-03-30 (§12). This pool is the trading venue for a token he holds.
- NOT present in the user's GitHub code or commits (GitHub code search + commit search + full fresh clone of LeanTrader-Bot grepped file-by-file, 2026-09-19 — zero hits for either address).

### A2 = `0x74dC05b8FB6EBe3b604993Cb3f63e25322880121` — Aerodrome Slipstream CL Gauge
- Verified contract "CLGauge" (Aerodrome concentrated-liquidity gauge), minimal proxy pattern. Implementation `0x434BCcaB043311a20b16021C137EA81702790f7B`.
- Created **2026-07-14** (block 48623973) by EOA `0x8f6bF4A948Af2Fc74eE34982C4435a7C013D1A52` via Safe `0x71b94911FD1CE621FC40970450004c544e5287a8`; deployed through Aerodrome CL-gauge factory `0x385293CaE378C813F16f0C1334d774AdDDf56AbB`. Creation tx `0xc1207fda12e93c71d01ec95530890b13e001325c3e4eb95dddf6ba6378e2653f`.
- First AERO: 1,605.63 from "Aerodrome: Voter" (Distribute All), 2026-07-16, tx `0x0d1657490cf8618ddf18f7bb8164700cfebba6ef27175f79af94349763155894`.
- First user deposit: 2026-07-16, `0xBB14c535f536e919ACC1dDDda4d63d7177096116` deposited Slipstream Position NFT #2625483, tx `0xfeda1bbac10efa7f4cd26769eb3d65201e84de4ee26064272387fcb6dc32dfd2`.
- Activity: 717 normal txns (Deposit / Withdraw / Get Reward), 2026-07-16 → 2026-09-19; 1,464 ERC-20 transfers (nearly all AERO). Holds **824.14 AERO (~$538)** in unclaimed rewards. A live, used gauge.
- No interaction found with the 7-address cluster in the data reviewed (caveat: full histories of suryaprakash.base.eth and `0x94f33454…` were not exhaustively scanned).

### Private Basescan tags (account "JTCOMBS") — NEW, needs user's confirmation
- The explorer session was logged into a Basescan account named **JTCOMBS** (presumed the user's). It carries private name tags — visible only to that account — on:
  - "JTCombs" → the gauge (A2) and `0x20fbc02b…` (user's wallet)
  - "JTCombs SW" → `0x4e962BB3889Bf030368F56810A9c96B83CB3E778` (the cbBTC/USDC arb pool)
  - "Jonathan Combs" → `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (a USDC proxy token contract; its creating address is also tagged "Jonathan Combs")
- `0xBB14c535…` (the gauge's first depositor) has Approve transactions to that "Contract Jonathan Combs" (`0x833589fC…`).
- Implication if confirmed: the user has been privately tracking/labeling these addresses himself — which **reopens the arb-pool relationship** ("JTCombs SW" on the pool we judged unrelated) and suggests a user-deployed USDC proxy contract. Treat as unverified until he confirms JTCOMBS is his account.

### Funding-chain revision — oneworldonecoin IS downstream of the user
- Newly traced chain: `0x20fbc02b…` (user) → `0xB4BD7D410543cB27f42c562ab3fF5DC12fBDd42F` (suryaprakash.base.eth, EOA, 2,467 txns) → `0x94f334549B6393c3BbbD89C505Da58b6884EF344` (EOA, 532 txns) → `0x2c34bf9d…` (oneworldonecoin.base.eth).
- **Revises the §12 verdict**: W1 is not "no link" — it sits three hops downstream of the user's wallet via suryaprakash.base.eth.
- suryaprakash.base.eth: EIP-7702 delegated to MetaMask delegator; recent activity is social/NFT (Farcade, Seaport, Binance).
