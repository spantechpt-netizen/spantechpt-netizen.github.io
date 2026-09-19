# Span Tech CRM · نظام سبان تك لإدارة العملاء وعروض الأسعار

A bilingual (Arabic / English) CRM and quotation system built for **Span Tech Contracting** —
post-tensioned slab contracting across **Saudi Arabia, Egypt and Qatar**.

It runs on your own server, all engineers sign in to the same database, and every
quotation that leaves the company comes out of the same controlled template — in
Arabic or English, with the maths done for you.

نظام متكامل لإدارة العملاء المستهدفين، ومتابعة التواصل، وإصدار عروض الأسعار
بنسختين عربية وإنجليزية، مع تحليلات كاملة — يعمل على سيرفر الشركة ويدخل عليه
جميع المهندسين.

---

## What it does

| Module | العربية | What you get |
|---|---|---|
| **Dashboard** | لوحة التحكم | Open pipeline, weighted value, win rate, overdue follow-ups, latest quotations |
| **Customers** | العملاء | Target customer database with country, type, sector, priority, source, account engineer, and multiple contacts per company |
| **Pipeline** | الفرص | Drag-and-drop stage board (new → qualified → quoted → negotiation → won/lost) with per-stage totals |
| **Follow-ups** | المتابعات | Reminder centre bucketed into overdue / today / upcoming, with call, meeting, email, WhatsApp and site-visit types |
| **Quotations** | عروض الأسعار | Near-fixed offer template with simple variables, automatic numbering, revisions, VAT per country, and print-ready Arabic **and** English documents |
| **Cost calculator** | حاسبة التكلفة | Strand price/ton, kg per m², anchors per ton, ducts, grout, labour, design, overheads → cost per m², margin, and a suggested price for your target margin |
| **Notifications** | الإشعارات | A bell with live alerts: follow-ups falling due, overdue follow-ups, customers who have gone quiet, quotations nearing expiry, records assigned to you, and quotation decisions. Optional desktop pop-ups |
| **Messages** | الرسايل | Internal threads between engineers, optionally pinned to a customer, opportunity or quotation |
| **Calendar** | الأجندة | Month and agenda views of every follow-up, plus a private feed URL you subscribe to in Outlook or Google Calendar |
| **Incoming requests** | الطلبات الواردة | Reads the company mailbox, spots quotation requests and client replies, extracts the customer and project from the email, and queues them for the manager to hand to an engineer |
| **Analytics** | التحليلات | Conversion funnel, monthly trend, win rate by country and by engineer, loss-reason analysis, and an average price-per-m² benchmark |
| **Settings** | الإعدادات | Company profile, per-country price book, editable quotation templates, and user management with roles |

### Multi-country out of the box

| | Saudi Arabia | Egypt | Qatar |
|---|---|---|---|
| Currency | SAR | EGP | QAR |
| VAT | 15% | 14% | 0% |
| Default validity | 10 days | 10 days | 15 days |

Selecting a country on a quotation applies that market's currency, VAT rate and
default rates automatically.

---

## Email intake

Point the CRM at the company mailbox and quotation requests stop living in
somebody's inbox.

**What it does.** Every few minutes it checks the mailbox over IMAP, ignores
newsletters, bounces and out-of-office replies, and for anything that asks for a
price, mentions post-tensioning, or is a reply from someone already in the CRM,
it reads out the customer, contact, project, area, country and project type and
files it under **Incoming requests**. The manager gets a notification, assigns it
to an engineer — who is notified in turn — and one button then creates the
customer, the contact and the opportunity from the extracted draft.

**Nothing is created automatically.** An email is a claim, not a fact. Extraction
fills in a form that a person checks and corrects before anything enters the CRM,
and the confidence score on each request says how much could actually be pinned
down.

### Extraction without AI, and with it

Out of the box it works offline with built-in rules: it matches the sender
against customers you already have (by contact address, then company domain,
then name), and reads the area (`9,800 m²`, `٤٧٦ متر مربع`, `3,200 sqm` all
work), the country, the project type, phone numbers and the project name.

Adding a **Claude API key** in *Settings → Mailboxes* turns on a second pass that
reads the whole email properly — much better with free Arabic prose — and writes
a one-line summary in both languages. The key is stored encrypted, never sent
back to the browser, and if the call fails the built-in rules still stand. Get a
key from [console.anthropic.com](https://console.anthropic.com).

### Requests that arrive somewhere else

Not everything comes by email. A WhatsApp message, a phone call, a conversation
on site — paste it into *Incoming requests → Add a WhatsApp request* and it
joins the same queue, with the same extraction, the same triage and the same
one-button conversion behind it. Give it the sender's number and the sender is
matched against customers already on file, comparing the last eight digits so
`+966 55 123 4477` and `0551234477` are the same person (eight rather than
nine, because Qatari numbers are only eight digits long).

The CRM is also installable as an app on a phone, which is what puts it in the
share sheet: on Android, share a WhatsApp message to Span Tech and the capture
form opens already filled in. On iOS the share sheet cannot reach a web app, so
there it is copy and paste. The service worker that makes the app installable
caches nothing on purpose — an offline cache would go on serving yesterday's
JavaScript after a deployment, which is a worse problem than the one it solves.

### Importing your past email

*Settings → Mailboxes → Import from past email* scans as far back as you like,
across whichever folders you name, and puts everything it finds in the same queue
for review. Use it once when you first connect a mailbox to pull in the clients
and projects you have already been discussing.

### Connecting a mailbox

You need IMAP details and an **app password** — not the account's own password:

| | Host | Port |
|---|---|---|
| Gmail / Google Workspace | `imap.gmail.com` | 993 |
| Microsoft 365 / Outlook | `outlook.office365.com` | 993 |
| cPanel / most hosts | `mail.yourdomain.com` | 993 |

Gmail app passwords are created under Google Account → Security → 2-Step
Verification → App passwords.

> **Microsoft 365:** Microsoft has been switching tenants off basic
> authentication, so an app password may not work on yours. If the connection
> test fails with an authentication error, check with whoever administers your
> tenant whether IMAP with app passwords is still permitted.

The CRM only ever **reads**. It never sends, never deletes, and fetches with
`BODY.PEEK`, so messages are not marked as read behind anyone's back. The
password is encrypted with a key derived from `SESSION_SECRET` — which means
rotating that secret requires re-entering mailbox passwords.

## Reminders and the calendar

A sweep runs on the server every 15 minutes (and once at start-up) and raises:

| Alert | When |
|---|---|
| Follow-up due soon | Inside each engineer's own lead time (default 24 hours) |
| Follow-up overdue | The moment its time passes |
| **Missed contact** | A live customer with no activity for N days (default 30) and nothing scheduled |
| Quotation expiring | Three days before its validity runs out |
| Quotation expired | Validity passed — the offer is also marked expired automatically |

Each alert fires once, not on every pass. Engineers set their own lead time and
missed-contact threshold from *Calendar → Link to Outlook / Google*.

### Subscribing a calendar

Every engineer gets a private feed URL (`/calendar/<token>.ics`). Pasting it into
Outlook, Google Calendar or Apple Calendar as a **subscribed calendar** makes
their follow-ups appear there with a 30-minute alarm, and it keeps itself up to
date — no OAuth and no third-party account.

The token in that URL is the credential, so treat the link as private; if it
leaks, generate a new one from the same dialog and the old link stops working.

> For Google Calendar to poll the feed, the server has to be reachable from the
> internet. On an intranet-only server, Outlook and Apple Calendar on the same
> network still work, as does the per-event `.ics` download.

## Branch details

The company operates in more than one country, and a quotation must carry the
office that issues it. *Settings → Company profile → Branch details* holds a
block per country:

| | Saudi Arabia | Egypt | Qatar |
|---|---|---|---|
| Trading name | SPAN TECH Contracting & Post Tensioning | SPAN TECH Contracting & Post Tensioning | SPAN TEC Trading & Contracting |
| Phone | 0504291572 | +20 100 9896731 | +974 60008582 |
| Email | Info@spantechksa.com | Info@spantechpt.com | sales@spantec-qa.com, finance@spantec-qa.com |
| Website | www.spantechksa.com | www.spantechpt.com | www.spantechpt.com |
| Registration | CR 7038269549 | — | C.R. 175473 |
| Address | Riyadh | Villa 119, Al Banafseg, M. Naguib St., New Cairo | Doha |
| Logo | `logo@2x.png` | `logo@2x.png` | `logo-qa@2x.png` |

A quotation prints the branch matching **its own country**, so a Saudi offer
carries the Saudi commercial registration and Riyadh address while an Egyptian
one carries the Cairo office — from one set of settings, with no separate
templates to keep in step. Qatar trades under its own name and its own mark,
so a Qatari offer is not the Saudi letterhead with a different phone number on
it: the logo, trading name and registration label all come from that branch.

Code sequences (`C-0007`, `OPP-0012`, `SPAN TECH P.T - 26 - 006`) are
reconciled against the highest code actually in each table on every start, so a
database seeded with demo data, restored from a backup or edited by hand cannot
hand out a code that is already taken.

A branch you have not filled in yet borrows the default branch's contact details
rather than printing blanks, **except for the commercial registration and VAT
number**: those are country-specific legal identifiers and never inherit, so a
Saudi CR can never appear on an Egyptian document.

## A note on the Arabic

The **interface** is written in Egyptian business Arabic, because that is how
the team actually talks. The **printed quotation deliberately stays in formal
MSA**, because it goes to clients in Saudi Arabia and Qatar — that wording lives
in `server/templates.js` and the print template, not in the UI dictionary, so the
two can never leak into each other.

## Requirements

* **Node.js 22.5 or newer** (it uses the built-in `node:sqlite` module), **or** Docker.
* Nothing else. **There are no npm dependencies** — no `npm install`, no build step.

Linux, Windows and macOS all work — it is plain Node with no native modules and
no shell scripts in the runtime path.

---

## Running it

### Just trying it out

```bash
npm run demo     # writes .env, seeds demo data, prints the logins
npm start
```

Or double-click `start.bat` on Windows / run `./start.sh` on macOS and Linux —
those check the Node version, do the above and open the browser. There is an
Arabic quickstart for non-technical users in [`docs/TRY-IT.md`](docs/TRY-IT.md).

### Option A — Docker (recommended for the company server)

```bash
git clone https://github.com/spantechpt-netizen/spantechpt-netizen.github.io.git spantech-crm
cd spantech-crm

# 1. Set a real session secret in docker-compose.yml
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"

# 2. Start it
docker compose up -d
```

`docker-compose.yml` binds the container to `127.0.0.1:8090`, so the CRM is only
reachable through the TLS proxy. To try it before the proxy exists, change that
line to `"8090:8090"` temporarily and open `http://<server-ip>:8090`.

### Option B — directly with Node

```bash
cp .env.example .env     # then edit SESSION_SECRET and the admin password
npm run check            # Node version, port free, data dir writable, secret set
npm start
```

`npm run check` matters most when the CRM is going onto a server that already
runs something else: it catches a Node too old for `node:sqlite`, a port another
application already holds, and a data directory the service account cannot write
to — each of which otherwise fails at start-up with a less obvious message.

Open `http://localhost:8090`.

### First sign-in

On an empty database the first administrator is created from your `.env`
(defaults: `admin@spantechksa.com` / `SpanTech@2026`).
**Change that password immediately**, then add your engineers under
*Settings → Users*.

### Demo data (for training / evaluation)

```bash
npm run seed -- --demo
```

Adds 6 customers, 7 opportunities, 5 quotations across all three countries and a
few follow-ups, plus three engineer logins (password `SpanTech@2026`). Clear it
later with `npm run reset`.

---

## Putting it on the network properly

> **Handing this to a server administrator?** There is a complete Arabic handover
> document for `crm.spantechpt.com` — DNS records, server specs, ports, TLS,
> firewall, backups and a sign-off checklist — in two versions:
> [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for Linux (systemd, nginx, certbot)
> and [`docs/DEPLOYMENT-WINDOWS.md`](docs/DEPLOYMENT-WINDOWS.md) for Windows
> Server (NSSM, IIS + ARR, win-acme). The DNS records and server specs are the
> same in both; only the service, proxy and certificate tooling differ.

The app listens on **port 8090** by default (`PORT` in `.env` to change it).
It is 8090 rather than the more usual 8080 because the server it is going on
already has 8080 taken by another application — see the handover documents.

The app speaks plain HTTP. Put a reverse proxy in front of it for TLS:

```nginx
server {
    listen 443 ssl;
    server_name crm.spantechpt.com;

    ssl_certificate     /etc/letsencrypt/live/crm.spantechpt.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.spantechpt.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8090;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Then set `SECURE_COOKIES=true` and restart, so session cookies are HTTPS-only.

### Running on plain HTTP

Supported, and the handover documents cover it, but know what it costs. Set
`SECURE_COOKIES=false` — leaving it `true` over HTTP means the browser never
returns the session cookie, so sign-in bounces straight back to the login screen
(the server now detects that combination and says so, rather than letting you
hunt for it).

Two built-in features stop working, because browsers only allow them in a
secure context: **sharing a WhatsApp message straight into the CRM** from
Android's share sheet, which needs the app installable, and **desktop
notifications**. The interface says so where each one lives rather than
offering a control that silently does nothing. Everything else works.

What travels in clear text is the part worth weighing: sign-in passwords,
every session cookie — anyone who captures one is signed in as that person —
and the quotations and customer data themselves. If the hostname is public and
nginx is already in front, `certbot --nginx -d <host>` is one free,
self-renewing command.

> **Note on GitHub Pages:** this repository is a GitHub Pages repo, but Pages only
> serves static files. It cannot run this application, because the CRM needs a
> server process and a shared database for all engineers to see the same data.
> Deploy it to the company server (or any small VPS) using one of the options above.

### Backups

Everything lives in one file: `data/spantech.db`.

```bash
npm run backup                  # -> ./backups/spantech-YYYY-MM-DD.db
npm run backup -- /backups      # or somewhere else
```

This is safe while the server is running and needs no `sqlite3` command-line
tool, so it works the same on Windows: `VACUUM INTO` writes a complete,
compacted snapshot at a single point in time. Copying the file with `cp` or
`copy` is **not** safe, because recent transactions are still in the `-wal`
file. Snapshots older than 30 days are pruned (`BACKUP_KEEP_DAYS` to change
that).

A nightly cron job or scheduled task running that is a complete backup
strategy — but test a restore once before you rely on it.

---

## Roles and permissions

A role sets the starting point:

| Role | الصلاحية | Starts with |
|---|---|---|
| `admin` | مدير النظام | Everything, including user management |
| `manager` | مدير | Every record and setting, deletions, margins, approving quotations |
| `engineer` | مهندس | Create and edit **their own** customers, opportunities, follow-ups and quotations |
| `viewer` | مشاهدة بس | Read-only |

**Then you tune it per person.** *Settings → Users → Edit* shows a capability
matrix grouped by module — view / create / edit / delete for each area, plus
things like *see every engineer's customers*, *see cost and margin*, *approve or
reject quotations*, and *reassign records*. Tick or untick any line and it
applies to that one employee, without changing their role or anyone else's.

Lines you have not touched follow the role, and are labelled *default* or
*off by default*; anything you override is highlighted and labelled *custom*, so
it is obvious at a glance what was changed for this person. The permission set is
recomputed from the database on every request, so a change takes effect
immediately without signing anyone out.

Two guardrails: the last active administrator cannot be demoted or disabled, and
an administrator can never lose user management — otherwise an installation
could be stranded with nobody able to fix it.

---

## The quotation

The offer is deliberately **near-fixed**: the scope of work, exclusions,
requirements from the main contractor, warranty terms, payment schedule and
conditions all come from a company-wide template (editable in
*Settings → Quotation templates*). Per offer you normally only change:

* client, contact, project name and location,
* the area in m² and the rate,
* the country (which sets currency and VAT),
* and optionally untick any scope clause that does not apply.

Each quotation prints in **Arabic (RTL)** and **English (LTR)** from the same data,
via your browser's Print → *Save as PDF*.

### What changed versus the previous offer document

The template was rebuilt from the existing Span Tech offer, keeping all the
technical content and fixing the things that cost credibility:

1. **The price no longer contradicts itself.** The old offer quoted "70 SAR/m²" in
   the text while the cost table below it used 66 SAR/m² (476 m² × 66 = 31,416).
   The headline rate is now read from the priced line item, so the two can never disagree.
2. **VAT is shown.** The old document said "prices exclude VAT" but never showed the
   VAT amount or the gross total. The new one shows subtotal → VAT → grand total.
3. **Amount in words**, in Arabic and English — standard practice on a commercial
   offer and effectively required for contract documents.
4. **Payment terms show real money**, not just percentages: 30% / 40% / 30% now
   print with the actual amount against each milestone.
5. **The validity date is calculated** ("valid until 17/09/2026") instead of
   "valid for 10 days", so there is no argument about when it expired.
6. **A signature and acceptance block** for both parties, turning the offer into
   something the client can sign and return.
7. **An exclusions section**, which the original lacked — the single most common
   source of scope disputes on PT packages.
8. **Consistent typography and structure**: numbered scope sections, proper
   letterhead, tables with repeating headers, and no half-empty pages.
9. **A running header and footer on every page**, carrying a real
   "Page 3 of 4" — see below.

### The page frame

The company details are split rather than repeated. The letterhead on page one
carries the identity — logo, trade name, tagline and the branch's commercial
registration and VAT number. The footer carries how to reach that branch —
address, phone, email and website — alongside the quotation number, the issue
date and the page count. Pages two onwards get a compact running header with
the company name and the quotation reference, so a page that gets separated
from the set still identifies itself.

All of it lives in CSS `@page` margin boxes, which means the browser repeats it
on every sheet and `counter(pages)` gives a true total: a client who receives
three pages of a four-page offer can tell. A faint logo watermark sits behind
the text on every page, light enough that it does not compete with it.

The internal cost calculator (strand, anchors, ducts, grout, labour, design,
overheads) is **never printed** — it exists so the engineer can see the margin
before sending, and so the company can benchmark its own pricing.

---

## Project layout

```
server/
  index.js        HTTP server, routing, static files
  db.js           SQLite connection, migrations, query helpers
  schema.sql      Database schema
  auth.js         scrypt password hashing, signed session cookies, roles
  pricing.js      Totals, cost model, Arabic/English amount-in-words
  templates.js    Default quotation content and per-country price book
  seed.js         First admin, default settings, optional demo data
  routes/         REST API, one module per resource
public/
  index.html      Single-page app shell
  assets/js/      Vanilla ES modules — no framework, no build
    i18n.js       Full Arabic/English dictionary and formatting
    charts.js     Dependency-free SVG charts
    views/        One module per screen
test/
  api.test.js     End-to-end API tests against a throwaway database
```

## Tests

```bash
npm test
```

Boots the real server against a temporary database and exercises authentication,
permissions, the pricing maths (including the 476 m² × 70 SAR case from the
original offer), quotation revisions, per-country VAT, follow-up buckets and
analytics.

---

## Before you go live — checklist

- [ ] Set a long random `SESSION_SECRET`.
- [ ] Change the default administrator password.
- [ ] Put the app behind HTTPS and set `SECURE_COOKIES=true`.
- [ ] Fill in *Settings → Company profile* (VAT number, phone, email, address).
- [ ] **Review *Settings → Price book*.** The seeded strand prices and default
      rates for Egypt and Qatar are placeholders — replace them with your real
      market figures before issuing offers.
- [ ] Add your engineers and set their roles.
- [ ] Schedule a nightly backup of `data/spantech.db`.
