# QuantForge — What You Need to Set Up

Things Claude **cannot** do for you (accounts, credentials, approvals). Do them in this order.
Each item says *when* it's needed, so you don't have to do everything up front.

> 🔒 Never paste API keys, secrets or tokens into chat, GitHub issues, or commits. Put them only in your local `.env` file (git-ignored).

---

## ✅ Step 1 — Required now (before milestone M1 / issue #2)

### 1.1 Install & log in to GitHub CLI
Lets Claude open PRs, link them to issues, and close issues per the workflow in Epic #1.

```bash
brew install gh
```

```bash
gh auth login
```
Choose: GitHub.com → HTTPS → Login with a web browser. Then verify:

```bash
gh auth status
```

### 1.2 Install Python 3.12 via uv
Your system Python is 3.9 (too old). `uv` is already installed:

```bash
uv python install 3.12
```

### 1.3 Allow GitHub Actions on the repo
GitHub → `appletiger0704/QuantForge` → **Settings → Actions → General** → "Allow all actions", and Workflow permissions → "Read and write". Needed so CI from #2 runs.

### 1.4 (Recommended) Protect `main`
Settings → Branches → Add rule for `main`: require PR + require status checks (`ci`) to pass. Claude will work on branches and open PRs; **you** review and merge.

### 1.5 Confirm the decisions in [PROJECT_PLAN.md §2](PROJECT_PLAN.md#2-tech-decisions-proposed-defaults)
Reply "OK" or tell me what to change (e.g. PostgreSQL instead of SQLite, a different strategy threshold, other watchlist symbols).

---

## 🟡 Step 2 — Needed later, when we reach that milestone

| When | What you do | Why |
|---|---|---|
| Each PR | Review → approve → merge on GitHub (or tell Claude "merge it") | Workflow: PR → Merge → Close |
| M7 / #8 (optional) | **Notion digest**: create an integration at https://www.notion.so/my-integrations → copy the *Internal Integration Secret* into `.env` as `NOTION_TOKEN=...`; create an empty "QuantForge Daily Digest" database, share it with the integration, put its ID in `.env` as `NOTION_DIGEST_DB_ID=...` | Opt-in daily summary; never touches your research master |
| M8 / #7 (optional) | Make sure **Docker Desktop** is running (already installed) and has ≥ 4 GB RAM | Airflow runs in Docker |
| M8 / #7 (optional) | Choose a notification channel (e.g. Discord/Slack/LINE webhook URL) → `.env` as `QF_ALERT_WEBHOOK=...` | Pipeline failure alerts |
| Any time | Tell Claude your preferred watchlist (default: 2330, 2317, 0050) | Sample universe |

---

## 🔵 Step 3 — Optional: Shioaji (永豐金) — issue #9

Core MVP works **without** this. Do it only if you want broker market data.

1. Confirm you have an eligible 永豐金證券 account; read https://sinotrade.github.io/zh/tutor/prepare/token/
2. In Sinotrade's official key-management page, create **API Key + Secret Key** with **market-data / minimum privileges only** — do **not** enable trading permissions.
3. Note the expiry date, IP restrictions, and any required signing/authorization steps.
4. Add to your local `.env` (never commit):
   ```
   SJ_API_KEY=...
   SJ_SECRET_KEY=...
   ```
5. Tell Claude "Shioaji keys are in .env" — Claude will run the read-only live test and only then mark #9 as VERIFIED.
6. If access is denied, just tell Claude; it will be documented as a limitation (TWSE/TPEx remains the source).

---

## 📋 How to work with Claude, step by step

1. Do **Step 1** above (≈10 minutes).
2. Tell Claude: **"Setup done, start #2."**
3. Claude creates `docs/tickets/2-project-foundation.md`, implements, runs tests, opens a PR linked to #2.
4. You review & merge the PR (or say "merge it").
5. Say **"next"** → Claude proceeds #3 → #4 → #5 → (#6 + #10) → #8 → #7, one PR per issue.
6. When a milestone in **Step 2** comes up, Claude will remind you what to set.
7. At the end, Claude runs the end-to-end check against the Epic #1 Definition of Done, and you close the Epic.

### `.env` template (Claude will commit this as `.env.example`, with empty values)
```
QF_DB_URL=sqlite:///data/quantforge.db
QF_TIMEZONE=Asia/Taipei
# optional
NOTION_TOKEN=
NOTION_DIGEST_DB_ID=
QF_ALERT_WEBHOOK=
SJ_API_KEY=
SJ_SECRET_KEY=
```
