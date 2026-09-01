# Save State / Qualification Status

Canonical project: **Operations Intelligence & Automation Platform**

## Current release

- Version: **0.3.1**
- Build: `OIAP-0.3.1-20260831-FIELDLOG1`
- Scope: field-log hygiene and evidence hardening.
- Baseline: exact v0.3.0 full archive.
- Qualification: source-tree and GitHub release gates passed. Norton-on exact-artifact acceptance remains a separate native-Windows check.


## v0.3.1 source-tree qualification

- 46/46 managed runtime files verified.
- 33/33 application/analytics/security tests passed.
- 32/32 governed platform checks passed.
- 5/5 launcher/runtime contract checks passed.
- 40/40 HTTP/auth/RBAC/security/logging checks passed.
- Browser acceptance passed with 10 assertions, 9 screenshots, 0 console errors, and 0 page errors.
- Doctor passed with 6 governed KPI definitions and 7 SLO measurements.
- Package preflight found 7 intentional duplicate-content build boundaries and 0 unresolved duplicate groups.

## Windows field evidence inherited from v0.3.0

The August 31 v0.3.0 manual support export SHA-256 `330300AF3623C98C789B4445D41087738BA5803D40142A3B18A0E2F37DB81425` proves the Windows package reached `http_ready`, passed 46/46 runtime identity, initialized the governed store, served the new v0.3.0 intelligence assets, authenticated the governed demo session, and returned governed APIs. It also exposed the diagnostic log-hygiene defect repaired in v0.3.1.

## Immediate rollback

Preserve exact v0.3.0 as the Windows field-confirmed functional rollback:

```text
Operations_Intelligence_Automation_Platform_v0.3.0_Portfolio_Foundation.zip
SHA-256: 84A3D9304CBF8A080B97D5C267902E8FCF49D6D1F21F62191A6F206805B1F754
```

Known v0.3.0 caveat: TLS/non-HTTP probes may leave escaped-insufficient extended characters in diagnostic logs; application behavior and release identity were unaffected.

## Older rollback references

- v0.2.1: `C1C07A932D564C373F809676268662EBB1A613B04CF017AAFAD0E9A8ABAE09BE`
- v0.2.0: `52CCD0808EA32D8FBC6F369DDACFAE6F2CB7E407DF5E423B3DA2E818734441C8`
- v0.1.1: `386147CEDBFA81187ACC16AEB3EE60D8EFE465A873D8DB55D8FF633C00710732`
- v0.1.0 full field-evidenced rollback: `7C47C89EA9E4B926BDABBA720BC35D2BBF3F008299810346EECC74DB0D8CC8BA`

Do not mix managed files between rollback versions; branch from whole verified archives.
