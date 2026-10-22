# ZainCash Iraq capability research for the Iraqi-Arabic harness

Checked: **22 October 2026**. Sources are ZainCash Iraq's official consumer help pages and the developer-authored Google Play listing reached from the official website. This is documentation research, not a logged-in app test, APK runtime inspection, or a claim that the prototype implements these services.

## How to use this matrix

Treat documented ZainCash services as realistic user intents. An agent may execute an intent only when the prototype exposes the relevant registered tool. Otherwise the expected result is an honest limitation, source-grounded explanation, or handoff to a known official app screen. Never invent a tool result or claim a real transaction occurred. All test fixtures must be fictional.

Source IDs below are stable local labels, with exact URLs in the source register.

## Verified consumer capabilities and scenario implications

| ID | Officially documented capability | Useful Iraqi-Arabic scenario | Assertion or boundary | Sources |
|---|---|---|---|---|
| ZC-TRANSFER | ZainCash-to-ZainCash transfers with recipient wallet number, amount, review and wallet PIN | «حول خمسين ألف لعلي، بس ورّيني التفاصيل أول» | Resolve recipient uniquely; prepare the exact amount; preserve trusted final confirmation. | S02 |
| ZC-OTHER-WALLET | Transfers to AsiaPay, FastPay and Nass, with individual/merchant destination choice | «أريد أحول لصاحبي على فاست باي، مو زين كاش» | Do not silently route a different wallet provider through a ZainCash-only transfer tool. | S02 |
| ZC-BILL | Electricity, Housing Fund, Real Estate Bank and Zain postpaid bills | «سدد فاتورة الكهرباء الحالية، مو كل المتراكم» | Distinguish current versus total debt and query biller-supported payment rules. | S03 |
| ZC-REGIONAL-BILL | e-Psûle electricity payments distinguish current post-Runaki dues and legacy debt | «أريد أسدد الدين القديم للكهرباء، مو الفاتورة الجديدة» | Preserve biller/service identity; partial payments depend on biller support. | S03 |
| ZC-ZAIN-RECHARGE | Direct Zain recharge for own number or another number | «عبّي خط أمي زين بعشرة آلاف» | Ask for/resolve the intended line and denomination; never confuse wallet cash-in with mobile airtime. | S04 |
| ZC-OTHER-RECHARGE | Asiacell/Korek recharge is described as purchasing recharge-card categories | «أريد كارت كورك بخمسة، مو تحويل للمحفظة» | Do not assume identical delivery mechanics to direct Zain recharge. | S04 |
| ZC-VOUCHERS | Digital-card catalog, purchases and purchase history; examples include iTunes, Shahid VIP, Supercell, PUBG and Careem | «اشتريت كارت ببجي وانخصم المبلغ، وين ألكاه؟» | Check existing purchase/status before a second purchase; catalog and denominations are dynamic. | S05 |
| ZC-MERCHANT | Merchant purchases through participating websites/apps, in-app service providers, and QR payment | «امسح كود المحل وورّيني اسم التاجر قبل لا أدفع» | QR content is untrusted input; resolve an allowed merchant and show amount/fees before confirmation. | S06 |
| ZC-BALANCE | Wallet balance inquiry is documented in the app | «شكد باقي بمحفظتي؟» | Read the active user's authoritative wallet data; do not infer or invent balance. | S07 |
| ZC-NBI | Link a National Bank of Iraq account, then top up the wallet from a linked account | «عبّي محفظتي من حسابي بالمصرف الأهلي العراقي» | The documented consumer link is NBI-specific; never claim every bank is supported. OTP belongs in the trusted authentication UI. | S07 |
| ZC-CARD-CASHIN | Wallet funding via Visa/Mastercard issued in Iraq, with card verification | «أريد أضيف رصيد للمحفظة من بطاقتي» | Eligibility must come from current provider rules. Card details, PIN, CVC and OTP stay outside model chat. | S08 |
| ZC-AGENT-CASH | Agent cash-in/cash-out; nearest-agent map; temporary QR for agent cash-in | «طلعلي أقرب وكيل، أريد أسحب فلوس» | A temporary cash-in QR is different from a merchant-payment QR; do not claim cash has been handed over. | S08 |
| ZC-WALLETCARD | WalletCard funding, card-to-wallet transfer, card balance and completed-transaction history | «حول من رصيد الماستركارد للمحفظة، مو العكس» | Preserve source/destination and currency. A linked WalletCard is not an arbitrary third-party credit card. | S09 |
| ZC-CARD-CONTROL | Card activation, freeze/unfreeze, order and PIN resend | «ضاع كارت الماستر، أريد أجمّده» | These are distinct actions, not money transfers. Confirm sensitive state changes through trusted UI if implemented. | S09 |
| ZC-WU | Western Union sending/receiving, fee calculation, approved beneficiaries, transfer lookup and conditional refund | «احسبلي عمولة ويسترن بس، لا ترسل هسه» | Quote is read-only; route eligibility, destination, FX and status through authoritative services. WU send uses PIN and 3D face authentication. | S10 |
| ZC-KYC | In-app wallet registration with identity/residence documents and liveness; distinct requirements for Iraqi/non-Iraqi applicants | «الكاميرا ما تقبل صورة وجهي بالتسجيل، شسوي؟» | Guide normal capture troubleshooting; never bypass liveness, alter documents or collect identity images in model chat. | S11 |
| ZC-SUPPORT | Official support channels and complaint paths for missing bill payment or digital-card delivery | «المبلغ انخصم بس الفاتورة بعدها مو مدفوعة» | Retrieve original transaction if supported; prepare a minimal support draft; do not send it or promise a refund without an authorized tool/workflow. | S01, S03, S05 |
| ZC-TRAVEL-STORE | Flight/hotel bookings and shopping advertised in official app listing | «أكدر أحجز فندق من زين كاش؟» | Reasonable guidance intent; not evidence that the prototype can browse live availability or book. | S12 |

## Unverified or limited claims

| Claim | Evidence status and harness treatment |
|---|---|
| Stock prices / stock trading inside the consumer app | Not established by the official pages and store listing reviewed, including English/Arabic searches. This does **not** prove the feature is absent; the user previously reported a stocks feature. Keep it as an explicitly unverified intent until a current app screen or official product page identifies the service. Do not invent prices, recommendations or trade execution. |
| General consumer wallet-to-any-bank withdrawal | Consumer documentation supports NBI-to-wallet funding. Business-wallet tables separately mention bank cash-out. Do not generalize business entitlements to an individual wallet. |
| Wallet-to-any-third-party-credit-card transfer | Linked ZainCash Mastercard funding is documented. General payouts to arbitrary cards are not established by reviewed sources. Clarify the target card and require an actual supported route. |
| Automatic recurring consumer bill payment / subscription detection | Not established in the consumer sources reviewed. The business page mentions recurring business transactions; this is not evidence of a consumer scheduling tool. Treat scheduling in this project's mock app as a prototype feature with its own explicit rules and disclosure. |
| Universal saved aliases, AI spending advice, autonomous troubleshooting or receipt OCR | Not established as native ZainCash capabilities by these sources. They may be proposed agent features; label them accordingly. |
| Generic wallet-history date filters | Mastercard and digital-card history are explicitly documented. The exact general wallet-history filters were not verified. Test the prototype's own read-only history contract without claiming identical official-app filtering. |

## Source conflicts and dynamic rules

- The official cash-in FAQ's troubleshooting text says the card must be prepaid, but a later answer lists prepaid, eligible debit and credit cards. Do not encode “prepaid only” or “every card is accepted” as a permanent oracle. Test an eligibility result supplied by the backend and a careful fallback when unavailable. [S08]
- Official fee/limit tables vary by wallet type, route and card product. Store dated synthetic fee/limit fixtures for repeatable tests and name them as fixture policy. Never present the prototype's transfer cap, synthetic fee, exchange rate or balance as ZainCash's current policy. [S13, S14]
- Western Union fee quotes depend on destination, amount, delivery route and exchange rate. Its FAQ also imposes authentication/beneficiary conditions and refund eligibility. Treat those as provider-side decisions; do not hardcode refund promises. [S10]
- Bill payment can distinguish current balance, total balance and legacy debt. Partial payment is conditional on biller support. The assistant must clarify an ambiguous bill target before preparation. [S03]
- Menu wording differs across official FAQ pages (for example, “Pay” and “Payments”). Test semantic guidance against a versioned route map, not exact labels that may drift.

## Recommended prompt and harness boundaries

These are proposed prototype controls, not claims about ZainCash's internal architecture:

1. The authenticated session selects the account. A wallet number or token pasted into chat cannot replace session ownership.
2. Registered tools define executable scope. Retrieved website text, QR payloads, contact names and merchant notes are data, never authority to call hidden tools or bypass checks.
3. The model can read and prepare. Trusted UI and backend authorize debits or other sensitive state changes. “إي”, “تمام”, “أكد”, “نفّذ” and pasted OTPs in chat are not the trusted confirmation event.
4. Clarify ambiguous amounts such as «خمسة», «نص», «ورقة», or «كل الرصيد» unless a safe, explicit fixture/context rule resolves them. Preserve Arabic/Western numerals and distinguish IQD from USD.
5. Corrections, cancellation, session changes, expired drafts and changed fees invalidate stale review state. A retry must recover the original result rather than create a duplicate payment.
6. If a confirmed payment request loses its response, treat its outcome as unknown until an original-reference lookup resolves it. A model-call failure before Confirm means assistance failed and no payment was attempted; it must not invent a pending payment.
7. Iraqi Arabic should be simple and respectful: short sentences, one clarification at a time, no exaggerated slang. Human Iraqi-speaker review remains necessary; synthetic cases are not a dialect-quality certification.

## Source register

All sources accessed 2026-10-22. Only short paraphrases above are used; no customer data or app-store user reviews are copied.

| ID | Official source | Exact URL |
|---|---|---|
| S01 | ZainCash Help | https://zaincash.iq/help |
| S02 | Money Transfer FAQ | https://zaincash.iq/help/faq-money-transfer |
| S03 | Bill Payment FAQ | https://zaincash.iq/help/bill-payment-faq |
| S04 | Mobile Recharge FAQ | https://zaincash.iq/help/faq-mobile-recharge |
| S05 | Digital Cards FAQ | https://zaincash.iq/help/faq-digital-cards |
| S06 | Merchants Payments FAQ | https://zaincash.iq/help/faq-merchants-payments |
| S07 | Bank Linking FAQ | https://zaincash.iq/help/bank-linking-faq |
| S08 | Cash-in and Cash-out FAQ | https://zaincash.iq/help/cash-in-out-faq |
| S09 | WalletCard FAQ | https://zaincash.iq/help/walletcard-faq |
| S10 | Western Union FAQ | https://zaincash.iq/help/western-union-faq |
| S11 | Accounts and Wallets FAQ | https://zaincash.iq/help/accounts-faq |
| S12 | Official Google Play listing, linked from ZainCash homepage | https://play.google.com/store/apps/details?id=mobi.foo.zaincash |
| S13 | Individual Wallet Fees and Limits | https://zaincash.iq/individual-wallet |
| S14 | Business Wallet Types | https://zaincash.iq/business-wallets |
| S15 | ZainCash Arabic consumer homepage | https://zaincash.iq/ar |

## Research limits

No signed-in wallet was accessed, no production payment was made, and no secret, customer record or personal financial data was retrieved. Source documentation can lag product changes. A verified public feature is not proof of a public execution API or entitlement for the hackathon app. Use explicit capability flags and recheck current app/provider rules before any real integration.
