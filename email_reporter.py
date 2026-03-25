"""
Voxa — Email Reporter automatique v1.0
Envoie le rapport PDF mensuel par email aux clients.

Usage :
    python3 email_reporter.py --client psg
    python3 email_reporter.py --client betclic
    python3 email_reporter.py --client all        # tous les clients

PythonAnywhere scheduler (1er du mois à 6h) :
    00 06 1 * *   python3 /home/lucsharper/Voxa/email_reporter.py --client all

Variables .env requises :
    SMTP_HOST      (ex: smtp.gmail.com)
    SMTP_PORT      (ex: 587)
    SMTP_USER      (ex: voxa@sharper-media.com)
    SMTP_PASSWORD  (ex: app_password_gmail)
    SMTP_FROM      (ex: Voxa GEO Intelligence <voxa@sharper-media.com>)

Config destinataires dans RECIPIENTS ci-dessous.
"""

import os
import sys
import argparse
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", f"Voxa GEO Intelligence <{SMTP_USER}>")

# Destinataires par client — à personnaliser
RECIPIENTS = {
    "psg": {
        "to": ["contact@psg.fr"],           # → remplacer par le bon contact
        "cc": ["luc@sharper-media.com"],
    },
    "betclic": {
        "to": ["nicolas@betclic.com"],      # → Nicolas / Etienne / Michael / Morad
        "cc": ["luc@sharper-media.com"],
    },
}

CLIENTS = {
    "psg":     {"name": "PSG",     "full": "Paris Saint-Germain"},
    "betclic": {"name": "Betclic", "full": "Betclic"},
}

# ─────────────────────────────────────────────
# EMAIL HTML TEMPLATE
# ─────────────────────────────────────────────

def build_html_body(client_key: str, month: str, geo_score: int = None) -> str:
    cfg = CLIENTS[client_key]
    score_str = f"{geo_score}/100" if geo_score else "—"
    score_color = "#16A34A" if (geo_score or 0) >= 70 else "#D97706"

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F5F9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:32px 16px;">
    <table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

      <!-- Header -->
      <tr><td style="background:#0B1D3A;padding:24px 32px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td><span style="font-size:22px;font-weight:800;color:#B8962E;">VOXA</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.5);margin-left:8px;text-transform:uppercase;letter-spacing:2px;">GEO Intelligence</span></td>
            <td align="right"><span style="font-size:11px;color:rgba(255,255,255,0.5);">{month}</span></td>
          </tr>
        </table>
      </td></tr>

      <!-- Score hero -->
      <tr><td style="padding:32px 32px 24px;border-bottom:1px solid #E5E7EB;">
        <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#9CA3AF;text-transform:uppercase;letter-spacing:2px;">RAPPORT GEO MENSUEL</p>
        <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#111827;">{cfg['full']}</h1>
        <p style="margin:0;font-size:14px;color:#4B5563;">Votre GEO Score du mois — rapport complet en pièce jointe.</p>
      </td></tr>

      <!-- KPI -->
      <tr><td style="padding:24px 32px;border-bottom:1px solid #E5E7EB;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="text-align:center;padding:16px;background:#F5EDD5;border-radius:8px;">
              <div style="font-size:42px;font-weight:800;color:{score_color};line-height:1;">{score_str}</div>
              <div style="font-size:11px;font-weight:700;color:#9CA3AF;text-transform:uppercase;letter-spacing:1px;margin-top:6px;">GEO Score global</div>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Body -->
      <tr><td style="padding:24px 32px;">
        <p style="margin:0 0 16px;color:#374151;font-size:14px;line-height:1.7;">
          Vous trouverez en pièce jointe votre rapport GEO mensuel complet, incluant :
        </p>
        <ul style="margin:0 0 20px;padding:0 0 0 20px;color:#374151;font-size:14px;line-height:2;">
          <li>GEO Score par marché et par catégorie de prompt</li>
          <li>Net Sentiment Score et benchmark concurrents</li>
          <li>Évolution sur les 4 dernières semaines</li>
          <li>5 recommandations actionnables du mois</li>
        </ul>
        <p style="margin:0;color:#374151;font-size:14px;line-height:1.7;">
          Votre dashboard live est accessible à tout moment pour suivre l'évolution en temps réel.
        </p>
      </td></tr>

      <!-- CTA -->
      <tr><td style="padding:0 32px 32px;" align="center">
        <a href="https://lucsharper.pythonanywhere.com" 
           style="display:inline-block;background:#0B1D3A;color:#ffffff;font-weight:700;font-size:14px;
                  padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:0.5px;">
          Ouvrir le dashboard live →
        </a>
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#F9FAFB;padding:16px 32px;border-top:1px solid #E5E7EB;">
        <p style="margin:0;font-size:11px;color:#9CA3AF;">
          Voxa GEO Intelligence · Sharper Media · <a href="mailto:luc@sharper-media.com" style="color:#B8962E;">luc@sharper-media.com</a>
          <br>Ce rapport est confidentiel et destiné exclusivement à {cfg['full']}.
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""


# ─────────────────────────────────────────────
# PDF GENERATOR
# ─────────────────────────────────────────────

def generate_pdf(client_key: str, month: str = None) -> str | None:
    """Génère le PDF rapport et retourne le chemin."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = ["python3", "report_generator.py", "--client", client_key]
    if month:
        cmd += ["--month", month]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=script_dir)
    if result.returncode != 0:
        print(f"  ✗ Erreur génération PDF : {result.stderr}")
        return None

    today = datetime.now().strftime("%Y-%m")
    name = CLIENTS[client_key]["name"]
    pdf_path = os.path.join(script_dir, f"Voxa_Report_{name}_{today}.pdf")
    return pdf_path if os.path.exists(pdf_path) else None


# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

def send_report(client_key: str, month: str = None, dry_run: bool = False) -> bool:
    """Génère et envoie le rapport par email."""
    if client_key not in CLIENTS:
        print(f"  ✗ Client inconnu : {client_key}")
        return False

    cfg = CLIENTS[client_key]
    recipients = RECIPIENTS.get(client_key, {})
    to_list = recipients.get("to", [])
    cc_list = recipients.get("cc", [])
    month_str = month or datetime.now().strftime("%B %Y")

    print(f"\n  Rapport {cfg['full']} · {month_str}")
    print(f"  Destinataires : {', '.join(to_list + cc_list)}")

    # 1. Générer le PDF
    print("  → Génération PDF...", end=" ")
    pdf_path = generate_pdf(client_key, month)
    if not pdf_path:
        return False
    print("✓")

    # 2. Construire l'email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Voxa · Rapport GEO {cfg['full']} · {month_str}"
    msg["From"]    = SMTP_FROM
    msg["To"]      = ", ".join(to_list)
    if cc_list:
        msg["Cc"]  = ", ".join(cc_list)

    html_body = build_html_body(client_key, month_str)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 3. Attacher le PDF
    with open(pdf_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment",
                        filename=os.path.basename(pdf_path))
        msg.attach(part)

    if dry_run:
        print("  [DRY RUN] Email construit, non envoyé.")
        print(f"  PDF : {pdf_path}")
        return True

    # 4. Envoyer
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  ✗ SMTP_USER ou SMTP_PASSWORD manquant dans .env")
        return False

    print("  → Envoi SMTP...", end=" ")
    try:
        all_recipients = to_list + cc_list
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(SMTP_USER, all_recipients, msg.as_string())
        print("✓")
        return True
    except Exception as e:
        print(f"✗\n  Erreur SMTP : {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa — Email Reporter")
    parser.add_argument("--client", required=True, choices=[*CLIENTS.keys(), "all"],
                        help="Client ou 'all'")
    parser.add_argument("--month", default=None,
                        help="Mois (ex: 2026-03), défaut = mois courant")
    parser.add_argument("--dry-run", action="store_true",
                        help="Génère le PDF sans envoyer l'email")
    args = parser.parse_args()

    print("\n" + "═" * 55)
    print("  VOXA — Email Reporter v1.0")
    mode = "DRY RUN — pas d'envoi réel" if args.dry_run else "Mode envoi réel"
    print(f"  {mode}")
    print("═" * 55)

    targets = list(CLIENTS.keys()) if args.client == "all" else [args.client]
    success = 0

    for client in targets:
        ok = send_report(client, args.month, dry_run=args.dry_run)
        if ok:
            success += 1

    print(f"\n  Résultat : {success}/{len(targets)} rapport(s) {'préparé(s)' if args.dry_run else 'envoyé(s)'}")
    print("═" * 55 + "\n")