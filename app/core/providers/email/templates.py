"""The three mails the backend sends by itself: the verification code, the
password reset, the invitation.

Base44's design as its mails arrive today (read from a real mailbox,
2026-09-29): one page for all three — a banner, a body of plain paragraphs, a
grey box that holds the mail's one action — and an html part alone, no text
part. The markup below is theirs, element for element.

ONE deliberate difference: Base44's banner is a PICTURE of the title, served
from its mail vendor's CDN. Here the banner is the title as text on the
picture's colours, so a migrated app's mail loads nothing from Base44.
"""

from __future__ import annotations

from html import escape

_P = 'font-family:Arial,Helvetica,sans-serif; font-size:16px; line-height:24px; color:#1a1a1a;'
_BUTTON = (
    '<table cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;"><tr>\n'
    '                        <td class="cta-btn" style="background-color:#312F2F; border-radius:8px;">\n'
    '                          <a href="{href}" style="display:block; padding:14px 30px; font-family:Arial,Helvetica,sans-serif; font-size:16px; line-height:1.2; color:#ffffff; text-decoration:none; white-space:nowrap;">{label}</a>\n'
    '                        </td></tr></table>'
)


def _page(title: str, preheader: str, banner: str, banner_top: tuple[int, int], body: str) -> str:
    """`banner_top`: the space above the title, on a wide screen and on a
    phone. Base44 drew each banner as its own picture, so the space differs
    per mail; each mail passes what its picture measures."""
    top, phone_top = banner_top
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{title}</title>
  <style>
    body {{ margin:0; padding:0; background-color:#EEECEB; }}
    table {{ border-collapse:collapse; }}
    img {{ border:0; display:block; }}
    a {{ color:#1a1a1a; }}
    .cta-btn:hover {{ background-color:#1a1a1a !important; }}
    a[x-apple-data-detectors] {{ color:inherit !important; text-decoration:none !important; font-size:inherit !important; font-family:inherit !important; font-weight:inherit !important; line-height:inherit !important; }}
    @media only screen and (max-width:600px) {{
      .email-container {{ width:100% !important; max-width:360px !important; }}
      .outer-padding  {{ padding:24px 14px !important; }}
      .body-pad       {{ padding:28px 24px !important; }}
      .banner         {{ padding:{phone_top}px 20px 19px 20px !important; font-size:40px !important; line-height:39px !important; letter-spacing:-0.7px !important; }}
      .banner br      {{ display:none !important; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:#EEECEB;">
  <div style="display:none; font-size:1px; color:#EEECEB; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden;">{preheader}</div>

  <table class="outer-table" width="100%" cellpadding="0" cellspacing="0" style="background-color:#EEECEB;">
    <tr>
      <td class="outer-padding" align="center" style="padding:40px 20px;">

        <table class="email-container" width="650" cellpadding="0" cellspacing="0" style="width:650px; max-width:650px; background-color:#ffffff;">

          <tr>
            <td class="banner" style="padding:{top}px 30px 35px 30px; background-color:#E2DED7; font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; font-size:60px; line-height:58px; font-weight:500; letter-spacing:-1px; color:#1E1E24;">{banner}</td>
          </tr>

          <tr>
            <td class="body-pad" style="padding:34px 30px 40px 30px; font-family:Arial,Helvetica,sans-serif; color:#1a1a1a;">
{body}
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""


def _greeting(recipient_email: str) -> str:
    return f'              <p style="margin:0 0 22px 0; {_P}">Hey {escape(recipient_email.split("@")[0])},</p>'


def _footnote(what: str) -> str:
    return (
        '              <p style="margin:30px 0 0 0; font-family:Arial,Helvetica,sans-serif; font-size:12px; line-height:18px; color:#a8a29a; text-align:center;">'
        f"This is a system-generated email for {what}. Replies to this email address are not monitored.</p>"
    )


def otp_email_html(app_name: str, recipient_email: str, otp: str, expiry_minutes: int) -> str:
    app = escape(app_name)
    body = f"""\
{_greeting(recipient_email)}
              <p style="margin:0 0 28px 0; {_P}">Welcome to {app}. Please verify your email address to complete your registration.</p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F4F2; border-radius:10px; margin:0 0 28px 0;">
                <tr><td align="center" style="padding:28px 20px;">
                  <div style="font-family:Arial,Helvetica,sans-serif; font-size:15px; color:#6b6b6b;">Your verification code</div>
                  <div style="font-family:Arial,Helvetica,sans-serif; font-size:38px; font-weight:700; color:#F15A29; letter-spacing:8px; padding-top:12px;">{escape(otp)}</div>
                </td></tr>
              </table>
              <p style="margin:0 0 28px 0; {_P}">This code will expire in <strong>{expiry_minutes} minutes</strong>, so be sure to use it soon.</p>
              <p style="margin:0 0 0 0; {_P}">See you there,<br>The {app} team</p>
{_footnote("an email verification code")}"""
    return _page(
        title="Verify your email",
        preheader=f"Use the code below to finish setting up your {app} account.",
        banner="Verify your email",
        banner_top=(67, 52),
        body=body,
    )


def reset_password_email_html(app_name: str, recipient_email: str, reset_url: str) -> str:
    app = escape(app_name)
    body = f"""\
{_greeting(recipient_email)}
              <p style="margin:0 0 26px 0; {_P}">We received a request to reset your password. If that was you, just click the button below to choose a new one:</p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F4F2; border-radius:10px; margin:0 0 28px 0;">
                <tr><td align="center" style="padding:30px 28px;">
                  {_BUTTON.format(href=escape(reset_url), label="Reset password")}
                  <table align="center" width="74%" cellpadding="0" cellspacing="0" style="margin:18px auto 0 auto;"><tr><td style="font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:20px; color:#8a8a8a; text-align:center;">If the button above doesn&rsquo;t work, you can copy and paste the button link into your browser</td></tr></table>
                </td></tr>
              </table>
              <p style="margin:0 0 18px 0; {_P}">For your security, this link will expire in <strong>1 hour.</strong></p>
              <p style="margin:0 0 28px 0; font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:20px; color:#8a8a8a;">If you didn&rsquo;t request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>
              <p style="margin:0 0 0 0; {_P}">Stay secure,<br>The {app} Team</p>
{_footnote("a password reset link")}"""
    return _page(
        title="Reset your password",
        preheader="Link expires in 1 hour",
        banner="Reset your password",
        banner_top=(67, 42),
        body=body,
    )


def invite_email_html(
    app_name: str,
    recipient_email: str,
    inviter_email: str,
    role: str,
    app_url: str,
    description: str,
) -> str:
    """`description` is the app's own description (the app record's
    `user_description`); an app without one gets the paragraph empty, as
    Base44 sends it."""
    app = escape(app_name)
    body = f"""\
{_greeting(recipient_email)}
              <p style="margin:0 0 28px 0; {_P}">{escape(inviter_email)} has invited you to join {app} with the role of {escape(role)}. We&rsquo;re excited to have you on board!</p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F4F2; border-radius:10px; margin:2px 0 28px 0;">
                <tr><td style="padding:30px 28px;">
                  <p style="margin:0 0 8px 0; font-family:Arial,Helvetica,sans-serif; font-size:16px; font-weight:700; color:#1a1a1a; text-align:center;">About {app}</p>
                  <p style="margin:0 0 22px 0; font-family:Arial,Helvetica,sans-serif; font-size:15px; line-height:22px; color:#4a4a4a; text-align:center;">{escape(description)}</p>
                  <table width="100%" cellpadding="0" cellspacing="0"><tr><td style="border-top:1px solid #1a1a1a; font-size:0; line-height:0;">&nbsp;</td></tr></table>
                  <p style="margin:22px 0 22px 0; font-family:Arial,Helvetica,sans-serif; font-size:15px; line-height:22px; color:#1a1a1a; text-align:center;">Ready to jump in? Click below to accept your invitation and start collaborating with your team.</p>
                  {_BUTTON.format(href=escape(app_url), label="Access app")}
                </td></tr>
              </table>
              <p style="margin:0; {_P}">Best,<br>The {app} team</p>"""
    return _page(
        title="You're invited to join the app",
        preheader=f"You've been invited to collaborate on {app}.",
        banner="You&rsquo;ve been invited <br>to join an&nbsp;app",
        banner_top=(45, 44),
        body=body,
    )


def message_notice_html(app_name: str, url: str) -> str:
    """The notice a link-delivered message sends (core/mail/link.py): the
    app's name and one button — nothing of the message. The same page as the
    three mails above."""
    app = escape(app_name)
    body = f"""\
              <p style="margin:0 0 26px 0; {_P}">{app} sent you a message.</p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F4F2; border-radius:10px; margin:0 0 28px 0;">
                <tr><td align="center" style="padding:30px 28px;">
                  {_BUTTON.format(href=escape(url), label="Open message")}
                </td></tr>
              </table>
              <p style="margin:0 0 0 0; {_P}">See you there,<br>The {app} team</p>
{_footnote("a message notice")}"""
    return _page(
        title="You have a new message",
        preheader=f"{app} sent you a message.",
        banner="You have a new message",
        banner_top=(67, 52),
        body=body,
    )
