# Public website

`docs/index.html` is the public Protoss landing page, with a scrollable product story and native animated
Probe SVGs. It links to the running app and Telegram bot; it does not execute trades or show frozen
account balances. `.github/workflows/pages.yml` publishes this directory on pushes to `main`.

The app source is in `web/`. Rebuild and restart the Mac host to update `app.protoss.trade`.
The browser gallery is `/#/probe`; the public landing page includes the same downloadable SVGs.
Brand sources are `brand/probe.svg` and `brand/ad.html`. Run `scripts/build_probe_svgs.py` to regenerate
SVG states and icon aliases. Favicon, Apple touch icon, install icons, and share preview assets are
mirrored from `web/public/` into this directory.

`scripts/static_demo.py` can still produce an explicitly labeled frozen dashboard for offline use.
It is no longer the public homepage generator.
