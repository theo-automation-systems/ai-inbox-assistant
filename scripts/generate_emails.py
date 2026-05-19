"""Generate fake dataset emails (run once if you need to refresh files)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "emails"
EMAILS_PER_FOLDER = 5

DATA: dict[str, list[tuple[str, str]]] = {
    "support": [
        (
            "Login failures after SSO cutover",
            """FROM: Laura Mitchell <laura.mitchell@northwind.io>
TO: enterprise-support@aurora.ai
SUBJECT: Login failures after SSO cutover
DATE: 2026-05-12
THREAD-ID: THR-SUP-90812
ATTACHMENTS: sso_error_timeline.pdf

Hi Aurora team,

Since yesterday's SSO migration roughly 14:30 UTC, ~40 users in our NYC finance pod cannot complete SAML assertions. They loop back to the login screen with error AAI-2048. IdP logs show successful authentication.

Can you confirm whether attribute mapping for departmentNumber changed? We need this restored before payroll reconciliation tomorrow morning.

Thanks,
Laura""",
        ),
        (
            "API rate limiting unexpectedly aggressive",
            """FROM: Devon Patel <devon.patel@brightcart.co>
TO: support@aurora.ai
SUBJECT: API rate limiting unexpectedly aggressive
DATE: 2026-05-13

Hello,

Our nightly inventory sync jobs began failing with HTTP 429 starting May 11. We did not change throughput. Project ID acct_771b.

Please advise if limits were tightened globally.

Devon""",
        ),
        (
            "Webhook retries flooding sandbox",
            """FROM: Casey Nguyen <casey.nguyen@pixelloft.io>
TO: support@aurora.ai
SUBJECT: Webhook retries flooding sandbox
DATE: 2026-05-14

Support,

Sandbox endpoint hit with duplicate webhook deliveries every ~30s for invoice.paid events starting today 09:10 PT. Signature validates.

Need guidance to pause retries while we debug listener.

Casey""",
        ),
        (
            "Broken CSV export for cohort report",
            """FROM: Jordan Ellis <jordan.ellis@helixlabs.com>
TO: support@aurora.ai
SUBJECT: Broken CSV export for cohort report
DATE: 2026-05-14

The cohort retention export truncates after row 5000 even when applying filters. Dashboard shows full dataset.

Ticket severity: high for our quarterly review deck due Monday.

Jordan""",
        ),
        (
            "Question about HIPAA BAA coverage",
            """FROM: Priya Shah <priya.shah@clearwater.health>
TO: legal-support@aurora.ai
SUBJECT: Question about HIPAA BAA coverage
DATE: 2026-05-15

Could you confirm whether our Enterprise Workspace includes an executed BAA as of renewal on April 1? Legal wants documentation before enabling PHI notes.

Thanks,
Priya""",
        ),
        (
            "Mobile push notifications delayed",
            """FROM: Miguel Alvarez <miguel.alvarez@fleetroute.co>
TO: support@aurora.ai
SUBJECT: Mobile push notifications delayed
DATE: 2026-05-15

Drivers report 10-25 minute delays on assignment pushes since build 3.12.1 on Android only.

Let me know if there is a known regression.

Miguel""",
        ),
        (
            "Cannot invite guest collaborators",
            """FROM: Riley Brooks <riley.brooks@northwind.io>
TO: support@aurora.ai
SUBJECT: Cannot invite guest collaborators
DATE: 2026-05-16

Guest invites send but recipients land on 403 when accepting. Domain allowlist shows *.consultopia.com approved.

Please advise urgently—board workshop tomorrow.

Riley""",
        ),
        (
            "Latency spikes on EU shard",
            """FROM: Sofia Martins <sofia.martins@blueanchor.eu>
TO: support@aurora.ai
SUBJECT: Latency spikes on EU shard
DATE: 2026-05-16

Observing P95 UI latency 4-8s intermittently on eu-central workspace EUW-88 between 11:00-13:00 CET.

Happy to share HAR files.

Sofia""",
        ),
        (
            "Billing portal shows wrong seat count",
            """FROM: Harper Quinn <harper.quinn@vectorrise.io>
TO: billing-support@aurora.ai
SUBJECT: Billing portal shows wrong seat count
DATE: 2026-05-17

Portal lists 312 seats while admin console shows 298 active after deprovisioning contractors Friday.

Need corrected invoice preview before May 20 close.

Harper""",
        ),
        (
            "Need rollback instructions for workflow pack",
            """FROM: Avery Cole <avery.cole@silverline.tech>
TO: support@aurora.ai
SUBJECT: Need rollback instructions for workflow pack
DATE: 2026-05-17

We deployed automation pack v17 and it created duplicate tasks on closed deals. Is there a documented rollback path besides restoring snapshot WF-309?

Avery""",
        ),
    ],
    "invoices": [
        (
            "Invoice INV-88321 — May subscription",
            """FROM: Accounts Payable <ap@cloudledger.com>
TO: billing@aurora.ai
SUBJECT: Invoice INV-88321 — May subscription
DATE: 2026-05-10
ATTACHMENTS: INV-88321.pdf

Please find attached invoice for May recurring subscription totaling USD 18,450.00 due Net 30.

Remit to routing on page 2.

Thanks,
CloudLedger AP""",
        ),
        (
            "Past due notice — PO 99402",
            """FROM: Collections <collections@vendoraxis.net>
TO: finance@aurora.ai
SUBJECT: Past due notice — PO 99402
DATE: 2026-05-11

Balance EUR 6,230.50 for PO 99402 is 12 days overdue. Reference invoice VA-44021.

Wire instructions attached.

VendorAxis Collections""",
        ),
        (
            "Credit memo CM-221 applied",
            """FROM: Billing Ops <billingops@aurora.ai>
TO: finance@aurora.ai
SUBJECT: Credit memo CM-221 applied
DATE: 2026-05-11

Credit memo CM-221 for USD 2,100.00 applied to invoice INV-88102 per SLA remediation case SLA-991.

No further action required unless disputed within 10 days.

Billing Ops""",
        ),
        (
            "AWS Marketplace seller disbursement",
            """FROM: AWS Marketplace <no-reply@marketplace.amazonaws.com>
TO: finance@aurora.ai
SUBJECT: AWS Marketplace seller disbursement
DATE: 2026-05-12

Disbursement of USD 42,118.33 scheduled May 15 for listing aurora-insights-pro.

ATTACHMENTS: remittance_detail.csv""",
        ),
        (
            "Quarterly true-up estimate",
            """FROM: Emma Clarke <emma.clarke@aurora.ai>
TO: finance@aurora.ai
SUBJECT: Quarterly true-up estimate
DATE: 2026-05-12

Finance preview: projected Q2 true-up GBP 11,400 due to seat growth in UK subsidiary.

Detailed workbook attached.

Emma""",
        ),
        (
            "Vendor onboarding — W-9 attached",
            """FROM: Procurement <procurement@aurora.ai>
TO: vendors@aurora.ai
SUBJECT: Vendor onboarding — W-9 attached
DATE: 2026-05-13

New vendor GreenSpruce Analytics requires payment setup. W-9 attached.

Expected first invoice USD 9,600 on June 1.

Procurement""",
        ),
        (
            "Expense report ER-556 reimbursement",
            """FROM: Payroll <payroll@aurora.ai>
TO: you@aurora.ai
SUBJECT: Expense report ER-556 reimbursement
DATE: 2026-05-13

Your NYC trip expenses USD 842.17 approved. Deposit scheduled May 17 payroll cycle.

Payroll""",
        ),
        (
            "Renewal quote QR-221 for Atlas Corp",
            """FROM: Revenue Ops <revops@aurora.ai>
TO: sales@aurora.ai
SUBJECT: Renewal quote QR-221 for Atlas Corp
DATE: 2026-05-14

Renewal ARR USD 240k with 8% uplift. Legal redlines pending.

RevOps""",
        ),
        (
            "Invoice discrepancy ticket FIN-771",
            """FROM: Controller Office <controller@aurora.ai>
TO: finance@aurora.ai
SUBJECT: Invoice discrepancy ticket FIN-771
DATE: 2026-05-14

Vendor billed twice for storage tier uplift in April. Delta USD 3,400 requires clawback letter.

Controller Office""",
        ),
        (
            "ACH confirmation — payment PMT-99331",
            """FROM: TreasuryBot <treasurybot@aurora.ai>
TO: finance@aurora.ai
SUBJECT: ACH confirmation — payment PMT-99331
DATE: 2026-05-15

ACH batch PMT-99331 successfully transmitted USD 57,900.00 to vendor CloudLedger.

TreasuryBot""",
        ),
    ],
    "meetings": [
        (
            "Calendar hold — QBR dry run",
            """FROM: Nina Ortiz <nina.ortiz@aurora.ai>
TO: exec-staff@aurora.ai
SUBJECT: Calendar hold — QBR dry run
DATE: 2026-05-16

Please hold Thu May 22 15:00-16:30 PT for internal QBR dry run. Agenda circulating Friday.

Nina""",
        ),
        (
            "Interview loop for Staff ML Engineer",
            """FROM: Talent <talent@aurora.ai>
TO: hiring-panel@aurora.ai
SUBJECT: Interview loop for Staff ML Engineer
DATE: 2026-05-16

Loop scheduled May 23 for candidate A. Park. Panel: systems design 10:00, coding 13:00.

Talent""",
        ),
        (
            "Customer workshop planning call",
            """FROM: Marcus Webb <marcus.webb@aurora.ai>
TO: cs-leads@aurora.ai
SUBJECT: Customer workshop planning call
DATE: 2026-05-17

Let's align Mon May 19 09:00 PT on workshop deck for Summit Retail.

Marcus""",
        ),
        (
            "Vendor security review touchpoint",
            """FROM: Security PMO <sec-pmo@aurora.ai>
TO: vendor-risk@aurora.ai
SUBJECT: Vendor security review touchpoint
DATE: 2026-05-17

Touch base Tue May 20 11:30 ET on GreenSpruce SOC2 gaps.

Security PMO""",
        ),
        (
            "Office hours — new analytics rollout",
            """FROM: Product Marketing <pmktg@aurora.ai>
TO: gtm@aurora.ai
SUBJECT: Office hours — new analytics rollout
DATE: 2026-05-18

Drop-in session Wed May 21 17:00 UTC for launch collateral questions.

PMKTG""",
        ),
        (
            "Board committee prep session",
            """FROM: Chief of Staff <cos@aurora.ai>
TO: leadership@aurora.ai
SUBJECT: Board committee prep session
DATE: 2026-05-18

Prep Fri May 23 08:00 PT for audit committee packet review.

CoS""",
        ),
        (
            "Design critique — inbox redesign",
            """FROM: Design Guild <design-guild@aurora.ai>
TO: design@aurora.ai
SUBJECT: Design critique — inbox redesign
DATE: 2026-05-19

Crit scheduled May 24 14:00 PT. Bring mobile flows.

Design Guild""",
        ),
        (
            "Weekly infra sync moved",
            """FROM: SRE Rotation <sre@aurora.ai>
TO: platform@aurora.ai
SUBJECT: Weekly infra sync moved
DATE: 2026-05-19

Infra sync moved to Thu May 22 18:00 UTC due to freeze window.

SRE""",
        ),
        (
            "Lunch & learn: EU AI Act primer",
            """FROM: Legal Education <legal-edu@aurora.ai>
TO: all@aurora.ai
SUBJECT: Lunch & learn: EU AI Act primer
DATE: 2026-05-20

Optional session May 21 12:30 CET in Berlin cafe floor + Zoom.

Legal Edu""",
        ),
        (
            "1:1 weekly slot adjustment",
            """FROM: Manager Notes <manager@aurora.ai>
TO: you@aurora.ai
SUBJECT: 1:1 weekly slot adjustment
DATE: 2026-05-20

Moving our 1:1 to Wednesdays 16:00 local starting next week.

Thanks""",
        ),
    ],
    "spam": [
        (
            "Congratulations! You won enterprise licensing",
            """FROM: PrizeDesk Offers <winner-not-real@promoclaim.xyz>
TO: you@aurora.ai
SUBJECT: Congratulations! You won enterprise licensing
DATE: 2026-05-10

Click http://bit.ly/not-legit-claim now to unlock unlimited seats. Limited time!!!

Unsubscribe maybe works.

PrizeDesk""",
        ),
        (
            "URGENT wire instructions update",
            """FROM: CFO Imposter <cfo.random@gmail.com>
TO: finance@aurora.ai
SUBJECT: URGENT wire instructions update
DATE: 2026-05-11

Please send urgent payment using new routing numbers immediately. Do not verify via phone.

Spam actor""",
        ),
        (
            "SEO audit report attached FREE",
            """FROM: GrowthSpammer <hello@growth-boost.ru>
TO: marketing@aurora.ai
SUBJECT: SEO audit report attached FREE
DATE: 2026-05-11

We guarantee page 1 ranking in 48 hours. Open invoice_seo.pdf.exe

GrowthSpammer""",
        ),
        (
            "You have (9) pending voicemails",
            """FROM: UnifiedVoice <notify@voiceclone.biz>
TO: you@aurora.ai
SUBJECT: You have (9) pending voicemails
DATE: 2026-05-12

Listen now or account suspended.

UnifiedVoice""",
        ),
        (
            "Exclusive crypto treasury hedge",
            """FROM: AlphaDesk <alpha@random-token.io>
TO: treasury@aurora.ai
SUBJECT: Exclusive crypto treasury hedge
DATE: 2026-05-12

Non-custodial yields 340% APY. DM seed phrase for onboarding.

AlphaDesk""",
        ),
        (
            "Invoice due — domain renewal",
            """FROM: Domain Registry Fake <support@domain-renew-fraud.co>
TO: it@aurora.ai
SUBJECT: Invoice due — domain renewal
DATE: 2026-05-13

Pay USD 499 immediately or lose aurora-ai-critical-domain.

Fake registry""",
        ),
        (
            "LinkedIn recruiter blast",
            """FROM: TalentBot 4821 <invite+bulk@inmail-copycat.net>
TO: you@aurora.ai
SUBJECT: LinkedIn recruiter blast
DATE: 2026-05-13

We reviewed your profile secret links inside tracking pixel heavy HTML.

TalentBot""",
        ),
        (
            "Miracle weight loss for founders",
            """FROM: WellnessSpam <deals@wellspam.biz>
TO: founders@aurora.ai
SUBJECT: Miracle weight loss for founders
DATE: 2026-05-14

Burn belly fat while closing Series C!!!!!

WellnessSpam""",
        ),
        (
            "Your parcel could not be delivered",
            """FROM: Courier Fake <info@parcel-scam.io>
TO: you@aurora.ai
SUBJECT: Your parcel could not be delivered
DATE: 2026-05-14

Pay customs fee USD 2.99 via suspicious portal.

Courier Fake""",
        ),
        (
            "Cheap OEM Microsoft licenses",
            """FROM: LicenseWarehouse <sales@licenseware.invalid>
TO: procurement@aurora.ai
SUBJECT: Cheap OEM Microsoft licenses
DATE: 2026-05-15

Volume keys PDF attached; ignore authenticity warnings.

LicenseWarehouse""",
        ),
    ],
    "urgent": [
        (
            "SEV-1: Payments API returning 500s",
            """FROM: Incident Commander <ic@sre.aurora.ai>
TO: eng-incidents@aurora.ai
SUBJECT: SEV-1: Payments API returning 500s
DATE: 2026-05-15

Incident INC-772 declared SEV-1 at 13:05 UTC. Error budget exhausted for checkout API.

War room Zoom bridge active.

IC""",
        ),
        (
            "Production DB failover triggered",
            """FROM: SRE On-call <oncall@sre.aurora.ai>
TO: platform@aurora.ai
SUBJECT: Production DB failover triggered
DATE: 2026-05-15

Automated failover completed on shard primary-us-east-1b. Investigating replication lag spikes.

SRE""",
        ),
        (
            "Customer threatening churn — SLA breach",
            """FROM: Executive Sponsor Desk <execdesk@aurora.ai>
TO: cs-leads@aurora.ai
SUBJECT: Customer threatening churn — SLA breach
DATE: 2026-05-16

Summit Retail VP escalating downtime credits; contractual penalty clause invoked if unresolved by EOD Friday.

ExecDesk""",
        ),
        (
            "Legal hold notice — preserve communications",
            """FROM: Legal <legal@aurora.ai>
TO: leadership@aurora.ai
SUBJECT: Legal hold notice — preserve communications
DATE: 2026-05-16

Effective immediately preserve all communications regarding Project Prism litigation matter PRISM-09.

Legal""",
        ),
        (
            "Security breach suspicion — leaked OAuth token",
            """FROM: Security Operations <secops@aurora.ai>
TO: eng-security@aurora.ai
SUBJECT: Security breach suspicion — leaked OAuth token
DATE: 2026-05-17

Potential leaked OAuth refresh token detected in public gist scrubbing. Rotate creds for integration IG-221 ASAP.

SecOps""",
        ),
        (
            "Regulator inquiry deadline tomorrow",
            """FROM: Regulatory Affairs <regaff@aurora.ai>
TO: legal@aurora.ai
SUBJECT: Regulator inquiry deadline tomorrow
DATE: 2026-05-17

FIN inquiry responses due May 18 09:00 local; incomplete drafts flagged red.

RegAff""",
        ),
        (
            "Data center cooling failure risk",
            """FROM: Facilities NOC <noc@aurora.ai>
TO: infra@aurora.ai
SUBJECT: Data center cooling failure risk
DATE: 2026-05-18

PDU maintenance overrun risking thermal thresholds within 2 hours unless workloads shifted.

NOC""",
        ),
        (
            "CEO briefing deck corrupted hours before board",
            """FROM: Chief of Staff <cos@aurora.ai>
TO: design@aurora.ai
SUBJECT: CEO briefing deck corrupted hours before board
DATE: 2026-05-18

Slide master corrupted 45 minutes before board dinner; need rescue NOW.

CoS""",
        ),
        (
            "Major prospect POC blocked on sandbox outage",
            """FROM: Sales Engineering <se@aurora.ai>
TO: eng-leads@aurora.ai
SUBJECT: Major prospect POC blocked on sandbox outage
DATE: 2026-05-19

Atlas Corp POC frozen due to sandbox instability; exec escalation requested before noon today.

SE""",
        ),
        (
            "Compliance audit finding — immediate remediation",
            """FROM: Internal Audit <audit@aurora.ai>
TO: security@aurora.ai
SUBJECT: Compliance audit finding — immediate remediation
DATE: 2026-05-19

Finding FA-17 requires MFA enforcement gap closed within 24 hours or SOC2 qualification at risk.

Audit""",
        ),
    ],
    "personal": [
        (
            "Coffee roastery pop-up Friday",
            """FROM: Workplace Experience <wx@aurora.ai>
TO: all-nyc@aurora.ai
SUBJECT: Coffee roastery pop-up Friday
DATE: 2026-05-12

Local roastery tasting Fri 09:00 in pantry B.

WX""",
        ),
        (
            "Reminder: submit PTO for Memorial Day",
            """FROM: HR Shared Services <hr@aurora.ai>
TO: all@aurora.ai
SUBJECT: Reminder: submit PTO for Memorial Day
DATE: 2026-05-13

Please finalize time-off requests before May 17 payroll lock.

HR""",
        ),
        (
            "Team lunch lottery winners",
            """FROM: Culture Crew <culture@aurora.ai>
TO: eng-nyc@aurora.ai
SUBJECT: Team lunch lottery winners
DATE: 2026-05-14

Congrats to pod Orion—lunch budget USD 400 this Friday.

Culture""",
        ),
        (
            "Parking garage closure notice",
            """FROM: Facilities <facilities@aurora.ai>
TO: nyc-office@aurora.ai
SUBJECT: Parking garage closure notice
DATE: 2026-05-14

Garage level 2 closed Sat-Sun for cleaning.

Facilities""",
        ),
        (
            "Welcome aboard kit shipped",
            """FROM: People Ops <peopleops@aurora.ai>
TO: you@aurora.ai
SUBJECT: Welcome aboard kit shipped
DATE: 2026-05-15

Your onboarding kit left warehouse today—tracking RB772991US.

People Ops""",
        ),
        (
            "ERG reading group — sci-fi May pick",
            """FROM: ERG Books <erg-books@aurora.ai>
TO: erg-members@aurora.ai
SUBJECT: ERG reading group — sci-fi May pick
DATE: 2026-05-15

Discussing "Translation State" chapters 1-6 Tue May 20 18:00.

ERG Books""",
        ),
        (
            "Desk cleanup week reminder",
            """FROM: Office Ops <officeops@aurora.ai>
TO: all@aurora.ai
SUBJECT: Desk cleanup week reminder
DATE: 2026-05-16

Please label equipment staying vs recycle stack.

Office Ops""",
        ),
        (
            "Bike locker lottery opens Monday",
            """FROM: Sustainability <green@aurora.ai>
TO: commuters@aurora.ai
SUBJECT: Bike locker lottery opens Monday
DATE: 2026-05-16

Lottery for summer lockers opens Mon 09:00.

Green""",
        ),
        (
            "Office closure holiday calendar sync",
            """FROM: Admin Bot <adminbot@aurora.ai>
TO: all@aurora.ai
SUBJECT: Office closure holiday calendar sync
DATE: 2026-05-17

Holiday closures synced to Google Calendar resource calendars.

Admin Bot""",
        ),
        (
            "Congrats on internal mobility approval",
            """FROM: People Partner <ppartner@aurora.ai>
TO: you@aurora.ai
SUBJECT: Congrats on internal mobility approval
DATE: 2026-05-17

Your transfer to Platform PM effective June 1 is approved.

People Partner""",
        ),
    ],
}


def main() -> None:
    total = 0
    for folder, emails in DATA.items():
        target = ROOT / folder
        target.mkdir(parents=True, exist_ok=True)
        for path in target.glob("email_*.txt"):
            path.unlink()
        for idx, (_subject, body) in enumerate(emails[:EMAILS_PER_FOLDER], start=1):
            path = target / f"email_{idx:02d}.txt"
            path.write_text(body.strip() + "\n", encoding="utf-8")
            total += 1
    print(f"Wrote {total} files under {ROOT} ({EMAILS_PER_FOLDER} per folder)")


if __name__ == "__main__":
    main()
