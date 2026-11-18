"""mailer.py - sends the encoding report as a styled HTML email.

Usage from encode.py:
    from mailer import mail

Credentials are read from the environment when mail() is called:
    source_mail, password, receiver
(encode.py already calls dotenv.load_dotenv(), so a .env file works.)

All CSS is inline and the layout is table-based on purpose: Gmail/Outlook strip
<style> blocks and ignore most modern CSS.
"""
import html
import os
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage
from typing import Optional

_COLORS = {
    "ok":    {"bg": "#16a34a", "soft": "#dcfce7", "text": "#166534", "label": "Encoding complete"},
    "warn":  {"bg": "#d97706", "soft": "#fef3c7", "text": "#92400e", "label": "Complete with warnings"},
    "error": {"bg": "#dc2626", "soft": "#fee2e2", "text": "#991b1b", "label": "Encoding failed"},
}


def _saved_pct(original, output) -> Optional[float]:
    try:
        return max(0.0, (1 - float(output) / float(original)) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _stat(label: str, value: str) -> str:
    return f"""
      <td align="center" style="padding:14px 6px;">
        <div style="font-size:22px;font-weight:700;color:#111827;">{value}</div>
        <div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#6b7280;margin-top:2px;">{label}</div>
      </td>"""


def _file_row(f: dict) -> str:
    esc = html.escape
    pct = _saved_pct(f.get("original_size"), f.get("size"))
    bar = ""
    if pct is not None:
        w = int(min(100, round(pct)))
        bar = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">
          <tr>
            <td style="background:#e5e7eb;border-radius:4px;height:6px;line-height:6px;font-size:0;">
              <table role="presentation" width="{w}%" cellpadding="0" cellspacing="0"><tr>
                <td style="background:#16a34a;border-radius:4px;height:6px;line-height:6px;font-size:0;">&nbsp;</td>
              </tr></table>
            </td>
          </tr>
        </table>"""

    saved_txt = f"{pct:.0f}% smaller" if pct is not None else ""
    meta = " &nbsp;&middot;&nbsp; ".join(
        esc(str(x)) for x in (
            f.get("resolution"),
            f"avg {f['bit_rate']}" if f.get("bit_rate") else None,
            f.get("elapsed"),
        ) if x
    )
    warn = ""
    if f.get("warning"):
        warn = f"""
        <div style="margin-top:8px;padding:8px 10px;background:{_COLORS['warn']['soft']};color:{_COLORS['warn']['text']};
                    border-radius:6px;font-size:12px;line-height:1.4;">&#9888; {esc(f['warning'])}</div>"""

    return f"""
    <tr>
      <td style="padding:14px 24px;border-top:1px solid #e5e7eb;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="font-size:14px;font-weight:600;color:#111827;word-break:break-all;">{esc(str(f.get('file_name')))}</td>
            <td align="right" style="font-size:12px;font-weight:600;color:#16a34a;white-space:nowrap;padding-left:12px;">{saved_txt}</td>
          </tr>
          <tr>
            <td colspan="2" style="font-size:13px;color:#4b5563;padding-top:3px;">
              {f.get('original_size')} MB &rarr; <strong style="color:#111827;">{f.get('size')} MB</strong>
            </td>
          </tr>
          <tr><td colspan="2" style="font-size:12px;color:#9ca3af;padding-top:2px;">{meta}</td></tr>
        </table>{bar}{warn}
      </td>
    </tr>"""


def build_mail_html(sDir: str, status: str, **kwargs) -> str:
    esc = html.escape
    c = _COLORS[status]
    files = kwargs.get("files", [])
    host = socket.gethostname()
    when = datetime.now().strftime("%d %b %Y, %H:%M")

    if status == "error":
        body = f"""
    <tr>
      <td style="padding:20px 24px;">
        <div style="font-size:13px;color:#6b7280;margin-bottom:8px;">ffmpeg / script output (last part):</div>
        <pre style="margin:0;padding:12px;background:#111827;color:#fca5a5;border-radius:8px;font-size:12px;
                    line-height:1.5;white-space:pre-wrap;word-break:break-word;font-family:Consolas,Menlo,monospace;">{esc(str(kwargs.get('error')))}</pre>
      </td>
    </tr>"""
    else:
        try:
            tot_orig = sum(float(f["original_size"]) for f in files)
            tot_out = sum(float(f["size"]) for f in files)
        except (KeyError, TypeError, ValueError):
            tot_orig = tot_out = 0.0
        saved = _saved_pct(tot_orig, tot_out)
        stats = (
            _stat("Files", str(len(files)))
            + _stat("Original", f"{tot_orig:.1f} MB")
            + _stat("Output", f"{tot_out:.1f} MB")
            + _stat("Saved", f"{saved:.0f}%" if saved is not None else "&ndash;")
        )
        params = " &nbsp;&middot;&nbsp; ".join(
            p for p in (
                f"CQ {esc(str(kwargs['cq']))}" if kwargs.get("cq") is not None else "",
                f"max {esc(str(kwargs['maxrate']))}" if kwargs.get("maxrate") else "",
            ) if p
        ) or "&ndash;"
        body = f"""
    <tr>
      <td style="background:#f9fafb;border-top:1px solid #e5e7eb;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{stats}</tr></table>
      </td>
    </tr>
    <tr>
      <td style="padding:12px 24px;font-size:12px;color:#6b7280;border-top:1px solid #e5e7eb;">
        Settings: {params}
      </td>
    </tr>
    {''.join(_file_row(f) for f in files)}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Encoding report</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;
                    font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
        <tr>
          <td style="background:{c['bg']};padding:22px 24px;">
            <div style="display:inline-block;padding:3px 10px;background:rgba(255,255,255,.2);border-radius:999px;
                        font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#ffffff;">{c['label']}</div>
            <div style="font-size:20px;font-weight:700;color:#ffffff;margin-top:10px;word-break:break-all;">{esc(str(sDir))}</div>
          </td>
        </tr>{body}
        <tr>
          <td style="padding:14px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;">
            {esc(host)} &nbsp;&middot;&nbsp; {when}
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_mail_text(sDir: str, status: str, **kwargs) -> str:
    """Plain-text fallback for clients that don't render HTML."""
    if status == "error":
        return f"An Error occured during the encoding.\nError: {kwargs.get('error')}"
    lines = [
        f"{_COLORS[status]['label']}: {sDir}",
        f"Settings: CQ {kwargs.get('cq', '-')}, max {kwargs.get('maxrate', '-')}",
        "",
    ]
    for f in kwargs.get("files", []):
        lines.append(
            f"File: {f.get('file_name')} - Avg bitrate: {f.get('bit_rate')} - "
            f"Size: {f.get('size')} MB - Original size: {f.get('original_size')} MB"
        )
        if f.get("warning"):
            lines.append(f"  WARNING: {f['warning']}")
    return "\n".join(lines)


def mail(sDir, **kwargs) -> None:
    if kwargs.get("nomail"):
        return
    smail = os.environ.get("source_mail")
    passwd = os.environ.get("password")
    rmail = os.environ.get("receiver")

    error = kwargs.get("error")
    has_warning = any(f.get("warning") for f in kwargs.get("files", []))
    status = "error" if error else "warn" if has_warning else "ok"

    subject = f"Encoding Progress of {sDir}"
    if status == "error":
        subject += " : ERROR"
    elif status == "warn":
        subject += " : WARNING"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smail
    msg["To"] = rmail
    msg.set_content(build_mail_text(sDir, status, **kwargs))                # plain-text part
    msg.add_alternative(build_mail_html(sDir, status, **kwargs), subtype="html")  # styled part

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smail, passwd)
        server.send_message(msg)
        print(f"Email has been sent to {rmail}")

    if error:
        exit()