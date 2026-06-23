"""Generate ALOS diagrams as PNGs (workflow + architecture + multi-product)."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BG = "#0b1020"
CARD = "#161c30"
STROKE = "#2b3450"
TEXT = "#e8ecf6"
MUTED = "#9aa6c0"
ACCENT = "#6ea8fe"
ACCENT2 = "#8b5cf6"
OK = "#34d399"
WARN = "#fbbf24"
PINK = "#f472b6"


def box(ax, x, y, w, h, label, fc=CARD, ec=STROKE, tc=TEXT, fs=10, bold=False, sub=None):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.10",
                       linewidth=1.3, edgecolor=ec, facecolor=fc, mutation_aspect=1)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2 + (0.08 if sub else 0), label, ha="center",
            va="center", color=tc, fontsize=fs, fontweight="bold" if bold else "normal",
            zorder=5)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.16, sub, ha="center", va="center",
                color=MUTED, fontsize=fs - 2.5, zorder=5)


def arrow(ax, x1, y1, x2, y2, color=ACCENT, style="-|>", lw=1.6, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                 mutation_scale=14, lw=lw, color=color, linestyle=ls,
                 shrinkA=2, shrinkB=2, zorder=1))


# ===========================================================================
# 1) KCC end-to-end workflow
# ===========================================================================
def workflow():
    fig, ax = plt.subplots(figsize=(15, 9), dpi=150)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 15); ax.set_ylim(0, 9); ax.axis("off")

    ax.text(0.4, 8.55, "ALOS — KCC Loan Lifecycle", color=TEXT, fontsize=20,
            fontweight="bold")
    ax.text(0.4, 8.15, "Event-sourced application · config-driven workflow · "
            "maker-checker + role gates · AI-optional · idempotent money",
            color=MUTED, fontsize=10.5)

    cols = [0.85, 6.1, 11.35]          # three columns
    w, h = 3.0, 1.0
    lane_y = {"acq": 6.45, "assess": 4.75, "dec": 3.05, "ful": 1.35}
    lanes = [("ACQUISITION", 6.4, "#1b2440"), ("ASSESSMENT", 4.7, "#1a2238"),
             ("DECISION & APPROVAL", 3.0, "#1b2440"), ("FULFILMENT (money)", 1.3, "#1a2238")]
    for name, y, c in lanes:
        ax.add_patch(FancyBboxPatch((0.3, y - 0.05), 14.4, 1.45,
                     boxstyle="round,pad=0,rounding_size=0.05", lw=0, facecolor=c, zorder=0))
        ax.text(0.5, y + 1.16, name, color=MUTED, fontsize=8.5, fontweight="bold")

    cx = lambda col: cols[col] + w / 2

    # ACQUISITION — left to right
    acq = ["Lead\nCreated", "Customer\nLinked", "KYC\nCompleted"]
    for i, label in enumerate(acq):
        box(ax, cols[i], lane_y["acq"], w, h, label, fs=10, bold=True)
    arrow(ax, cols[0] + w, lane_y["acq"] + h/2, cols[1], lane_y["acq"] + h/2)
    arrow(ax, cols[1] + w, lane_y["acq"] + h/2, cols[2], lane_y["acq"] + h/2)

    # ASSESSMENT — right to left (continues from KYC, col2)
    box(ax, cols[2], lane_y["assess"], w, h, "Eligibility\nComputed (det.)", fs=9.5, bold=True, ec=ACCENT)
    box(ax, cols[1], lane_y["assess"], w, h, "Underwriting\nRisk·Fraud·Comp", fs=9.5, bold=True, ec=PINK)
    box(ax, cols[0], lane_y["assess"], w, h, "Credit Memo\n(AI optional)", fs=9.5, bold=True, ec=ACCENT2)
    arrow(ax, cx(2), lane_y["acq"], cx(2), lane_y["assess"] + h, color=MUTED)   # down
    arrow(ax, cols[2], lane_y["assess"] + h/2, cols[1] + w, lane_y["assess"] + h/2, color=PINK)
    arrow(ax, cols[1], lane_y["assess"] + h/2, cols[0] + w, lane_y["assess"] + h/2, color=ACCENT2)

    # DECISION — left to right (continues from Memo, col0)
    dec = [("Maker\nReview", ACCENT), ("Checker\nReview", WARN), ("Sanction\n(authority)", WARN)]
    for i, (label, ec) in enumerate(dec):
        box(ax, cols[i], lane_y["dec"], w, h, label, fs=10, bold=True, ec=WARN)
    arrow(ax, cx(0), lane_y["assess"], cx(0), lane_y["dec"] + h, color=ACCENT2)  # down
    arrow(ax, cols[0] + w, lane_y["dec"] + h/2, cols[1], lane_y["dec"] + h/2, color=WARN)
    arrow(ax, cols[1] + w, lane_y["dec"] + h/2, cols[2], lane_y["dec"] + h/2, color=WARN)

    # FULFILMENT — right to left (continues from Sanction, col2)
    box(ax, cols[2], lane_y["ful"], w, h, "Documents\nNESL·eStamp·eSign", fs=9, bold=True, ec=OK)
    box(ax, cols[1], lane_y["ful"], w, h, "Disburse\n(idempotent)", fs=9.5, bold=True, ec=OK)
    box(ax, cols[0], lane_y["ful"], w, h, "CBS Posting\n+ reconcile", fs=9.5, bold=True, ec=OK)
    arrow(ax, cx(2), lane_y["dec"], cx(2), lane_y["ful"] + h, color=WARN)        # down
    arrow(ax, cols[2], lane_y["ful"] + h/2, cols[1] + w, lane_y["ful"] + h/2, color=OK)
    arrow(ax, cols[1], lane_y["ful"] + h/2, cols[0] + w, lane_y["ful"] + h/2, color=OK)

    # RENEWAL loop: CBS (col0) back up to Eligibility (col2), dashed
    arrow(ax, cols[0], lane_y["ful"] + h/2, 0.45, lane_y["ful"] + h/2, color=PINK, ls=(0, (4, 2)))
    arrow(ax, 0.45, lane_y["ful"] + h/2, 0.45, 7.7, color=PINK, ls=(0, (4, 2)))
    arrow(ax, 0.45, 7.7, cx(2), 7.7, color=PINK, ls=(0, (4, 2)))
    arrow(ax, cx(2), 7.7, cx(2), lane_y["assess"] + h, color=PINK, ls=(0, (4, 2)))
    ax.text(7.6, 7.76, "RENEWAL — re-validate & recompute (its own product + workflow)",
            color=PINK, fontsize=8.5, ha="center", va="bottom")

    # legend
    leg = [("deterministic / money", OK), ("AI-optional (fallback)", ACCENT2),
           ("role / maker-checker gate", WARN), ("renewal loop", PINK)]
    for i, (t, c) in enumerate(leg):
        ax.add_patch(plt.Rectangle((0.6 + i * 3.5, 0.35), 0.25, 0.18, color=c))
        ax.text(0.95 + i * 3.5, 0.44, t, color=MUTED, fontsize=8.5, va="center")

    plt.tight_layout()
    fig.savefig("/home/user/KCC/docs/diagrams/kcc-workflow.png",
                facecolor=BG, bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
# 2) System architecture
# ===========================================================================
def architecture():
    fig, ax = plt.subplots(figsize=(14, 9), dpi=150)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 14); ax.set_ylim(0, 9); ax.axis("off")

    ax.text(0.4, 8.55, "ALOS — System Architecture", color=TEXT, fontsize=20,
            fontweight="bold")
    ax.text(0.4, 8.15, "Modular monolith (ADR-0001) · selective event sourcing + "
            "outbox (ADR-0002) · Postgres RLS (ADR-0003)", color=MUTED, fontsize=10)

    # clients
    box(ax, 0.5, 7.0, 5.6, 0.9, "Web workspace (Next.js-style)", ec=ACCENT,
        sub="timeline · health · risk panel · product selector")
    box(ax, 6.4, 7.0, 5.6, 0.9, "Field PWA (offline)", ec=ACCENT,
        sub="IndexedDB capture · background sync")
    arrow(ax, 6.3, 6.95, 6.3, 6.35, color=MUTED)
    ax.text(6.55, 6.62, "HTTPS · OIDC · tenant headers", color=MUTED, fontsize=8)

    # API monolith
    box(ax, 0.5, 4.35, 11.5, 1.9, "", fc="#10182b", ec=ACCENT)
    ax.text(6.25, 6.0, "ALOS API — Modular Monolith (FastAPI)", color=TEXT,
            fontsize=12, fontweight="bold", ha="center")
    mods = ["Application\n(event-sourced)", "Assessment\nKCC + Dairy", "Underwriting\nRisk·Fraud·Comp",
            "Credit Memo\n(AI)", "Documentation\nsaga", "Disbursement\n+ recon"]
    for i, m in enumerate(mods):
        box(ax, 0.75 + i * 1.85, 4.55, 1.7, 0.95, m, fc=CARD, fs=7.8, ec=STROKE)
    ax.text(6.25, 4.18, "platform kernel: tenancy(RLS) · events · audit(hash-chain) · "
            "workflow engine · maker-checker · idempotency · integration ports",
            color=MUTED, fontsize=8, ha="center")

    # data stores
    stores = [("PostgreSQL", "system of record\nevents · audit · outbox", OK, 0.5),
              ("Redis", "cache · locks\nidempotency", ACCENT, 3.05),
              ("Kafka", "event bus\n(via outbox)", ACCENT2, 5.6),
              ("Elasticsearch", "read / search\nprojections", ACCENT, 8.15),
              ("MinIO / S3", "documents\n(WORM)", MUTED, 10.7)]
    for name, sub, c, x in stores:
        box(ax, x, 2.5, 2.3, 1.05, name, ec=c, sub=sub, fs=9.5, bold=True)
    arrow(ax, 6.25, 4.35, 6.25, 3.6, color=MUTED)

    # integrations
    box(ax, 0.5, 0.6, 11.5, 1.2, "", fc="#10182b", ec=WARN)
    ax.text(6.25, 1.55, "Integration adapters (mock · sandbox · prod) — retry · "
            "circuit-breaker · idempotency · audit", color=WARN, fontsize=10,
            fontweight="bold", ha="center")
    exts = "Aadhaar · PAN · CKYC · KYC(sandbox✓) · NESL · eStamp · eSign · " \
           "Land Records · CBS · Bureau · PM-KISAN · SMS/WhatsApp"
    ax.text(6.25, 1.0, exts, color=MUTED, fontsize=8.5, ha="center")
    arrow(ax, 6.25, 2.5, 6.25, 1.8, color=WARN)

    # AI sidecar
    box(ax, 12.2, 4.35, 1.5, 1.9, "AI\norchestrator", ec=ACCENT2, fc="#1a1430",
        sub="agents +\nguardrails")
    arrow(ax, 12.2, 5.3, 12.0, 5.3, color=ACCENT2, style="<|-|>")

    plt.tight_layout()
    fig.savefig("/home/user/KCC/docs/diagrams/architecture.png",
                facecolor=BG, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import os
    os.makedirs("/home/user/KCC/docs/diagrams", exist_ok=True)
    workflow()
    architecture()
    print("diagrams written")
