# Telegram OCR Bot

Send a photo, a scan, or a PDF — get the text back. Built to be deployed and left running, not demoed once.

Handles the things that usually break OCR bots in the wild: Telegram's 4096-character message cap, multi-photo albums arriving as separate out-of-order updates, phone photos that are skewed and unevenly lit, one user flooding the worker pool, and language packs that aren't installed.

---

## Quick start

```bash
git clone <your-repo> && cd telegram-ocr-bot
cp .env.example .env          # paste your token from @BotFather into BOT_TOKEN
docker compose up -d
docker compose logs -f bot
```

That's a working bot. Long polling by default, so no domain or TLS needed.

Running without Docker:

```bash
# Debian/Ubuntu — install the language packs you actually need
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-khm poppler-utils

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # set BOT_TOKEN
python -m bot
```

On macOS: `brew install tesseract tesseract-lang poppler`.

---

## What it does

| | |
|---|---|
| **Input** | Photos, image files (JPG/PNG/WebP/TIFF/BMP), PDFs, and multi-photo albums |
| **Output** | Text in chat (tap-to-copy `<pre>` block), `.txt`, `.docx`, or searchable PDF |
| **Engines** | Tesseract (free, local) and an optional vision-model engine for handwriting and hard photos |
| **Languages** | Any Tesseract language pack; `/lang eng+khm` for mixed documents |
| **Preprocessing** | EXIF rotation, deskew, denoise, CLAHE, adaptive threshold |
| **Quality signal** | Per-page confidence, with a proofread warning below 70% |
| **Per user** | Daily page quota, per-minute burst limit, tier (free/premium) |
| **History** | `/search invoice` finds text from past scans, auto-erased after 30 days |
| **Admin** | `/stats`, `/block`, `/unblock`, `/grant <id> premium` |

### Commands

`/start` · `/help` · `/lang` · `/engine` · `/format` · `/settings` · `/search` · `/quota` · `/privacy` · `/forgetme` · `/cancel`

---

## Configuration

Everything is environment variables — see `.env.example` for the full annotated list. The ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | — | Required. From [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | — | Comma-separated user IDs; unlocks admin commands |
| `WEBHOOK_BASE` | empty | Empty = long polling. Set to `https://your.domain` for webhooks |
| `DEFAULT_LANGS` | `eng` | Tesseract codes, `+` separated |
| `OCR_CONCURRENCY` | `4` | Keep at or below your CPU count — OCR is CPU-bound |
| `FREE_DAILY_PAGES` | `30` | Per-user daily quota |
| `BURST_PER_MINUTE` | `12` | Token bucket, per user |
| `ANTHROPIC_API_KEY` | empty | Blank disables the premium engine entirely |
| `STORE_TEXT_HISTORY` | `true` | Set `false` to store no extracted text at all |
| `MAX_FILE_MB` | `20` | Hard Bot API limit; raise only with a local Bot API server |

### Adding languages

Language packs are Debian packages. Edit the `TESSERACT_LANGS` build arg in the `Dockerfile`:

```dockerfile
ARG TESSERACT_LANGS="tesseract-ocr-eng tesseract-ocr-khm tesseract-ocr-ita"
```

Then `docker compose build`. Users pick with `/lang`. Codes are ISO 639-2 (`khm`, `tha`, `vie`, `chi_sim`, `jpn`, `ara`). `tesseract --list-langs` shows what's installed; the bot rejects codes that aren't and tells the user which.

Khmer, Thai, Lao and Burmese are worth calling out — they work, but accuracy on phone photos is noticeably below Latin scripts. If that's your main use case, the vision engine is a large step up and worth making the default.

---

## Deploying with webhooks

Long polling is fine up to a few thousand users. Beyond that, webhooks cut latency and API load.

```bash
# .env
WEBHOOK_BASE=https://ocr.example.com
WEBHOOK_SECRET=$(openssl rand -hex 32)
```

Put any TLS-terminating reverse proxy in front. Caddy is the shortest path:

```caddyfile
ocr.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

The bot registers the webhook on startup and exposes `GET /health` for your load balancer or Docker healthcheck.

---

## Architecture

```
bot/
├── app.py              composition root — wiring, webhook/polling, lifecycle
├── config.py           env → typed settings (pydantic)
├── db.py               SQLite: users, jobs, usage, retention
├── middlewares.py      user context · throttling · album batching
├── export.py           chunking, escaping, .txt/.docx
├── keyboards.py        inline keyboards
├── texts.py            all user-facing copy (en, km)
├── handlers/
│   ├── commands.py     settings, language, quota, search
│   ├── ocr.py          the actual job: media in → text out
│   └── admin.py        admin commands + global error handler
└── ocr/
    ├── base.py         OcrEngine interface, OcrResult
    ├── tesseract.py    free engine
    ├── vision.py       premium engine
    ├── preprocess.py   deskew, denoise, threshold
    └── pipeline.py     registry, concurrency, decoding
```

A few decisions worth knowing about:

**Album batching.** Telegram delivers a 10-photo album as 10 separate updates sharing a `media_group_id`. Naively that's 10 OCR jobs and 10 disordered replies. `AlbumMiddleware` buffers on the first update, waits ~1.2s for siblings, sorts by `message_id` and fires the handler once with the full set. This is what makes "photograph a whole book chapter" work.

**A semaphore, not a queue.** `OCR_CONCURRENCY` bounds simultaneous OCR work so a burst of uploads can't pin every core and make `/start` time out. Tesseract is blocking C code, so it runs via `asyncio.to_thread`. If you outgrow one box, replace the semaphore with Celery or arq and keep everything else.

**Preprocessing never raises.** A failure there falls back to the original image rather than failing the job — degraded output beats no output.

**Engines are pluggable.** Adding PaddleOCR, Google Vision or Azure Document Intelligence means one class implementing `OcrEngine` plus a line in `pipeline.py`. Nothing in the handlers changes.

**SQLite on purpose.** The workload is write-light and this keeps deployment to a single container with a mounted volume. WAL mode is on. If you outgrow it, `db.py` is the only module to rewrite.

---

## Testing

```bash
pytest -q      # 17 tests: export, chunking, throttling, album batching, DB, OCR round-trip
```

The OCR tests render text to an image, rotate it, and assert it comes back — so they catch preprocessing regressions, not just import errors.

---

## Operations

**Sizing.** Tesseract uses roughly 1 CPU-second per page at 200 DPI and a few hundred MB peak. Two cores comfortably handles a few thousand pages a day. Watch `avg_ms_24h` in `/stats` — if it climbs, you're queueing on the semaphore.

**Logs.** Set `LOG_JSON=true` in production; job records include user, engine and duration.

**Backups.** Everything is in `data/bot.sqlite3`. Back it up with `sqlite3 data/bot.sqlite3 ".backup /backup/bot.sqlite3"` — plain `cp` on a live WAL database can give you a torn copy.

**Privacy.** Images are processed in memory and never written to disk. Extracted text is retained for `HISTORY_RETENTION_DAYS` so `/search` works, then wiped by an hourly worker; `/forgetme` wipes on demand. `/privacy` states all of this to users. Take it seriously — people will send this bot passports, bank statements and medical records. If you don't need `/search`, set `STORE_TEXT_HISTORY=false` and store nothing.

**Costs.** Tesseract is free beyond the VPS (~$5–10/month). The vision engine runs roughly $0.003–0.01 per page — which is why it's gated behind `/engine` and a separate quota rather than being the default.

---

## Extending

Natural next steps, in rough order of payoff:

- **Translate after OCR** — the highest-value addition for a Cambodia/SEA user base. Menus, signs, official forms.
- **Structured extraction** — receipt → itemised JSON, business card → vCard, invoice → spreadsheet row. This is the part people pay for; the vision engine already returns text you can prompt into JSON.
- **Telegram Stars** for paid tiers — the required payment rail for digital goods in bots. `tier` and quota plumbing is already in the schema.
- **Table detection → CSV.**
- **LLM post-correction** — fix hyphenation, rejoin broken lines, resolve `rn`→`m` confusions. Big lift in perceived quality on top of Tesseract.
- **Inline mode** so the bot works inside any chat.

## Licence

MIT — do what you like with it.
